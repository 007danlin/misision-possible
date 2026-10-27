"""Bounded public-page adapter. No authentication, hidden APIs or invented reviews."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse, urljoin, urljoin
import httpx
from .ostrovok import PageData
from .tools import ToolError

CACHE = Path(os.getenv('HOTEL_CONTENT_CACHE', str(Path(tempfile.gettempdir()) / 'oplan-public-content-v2')))
THEMES = {'Тишина':r'тишин|тихо|шум|слыш|звукоизол', 'Чистота':r'чист|гряз|уборк|пыл', 'Питание':r'завтрак|питан|еда|еды|вкус|ресторан|меню', 'С детьми':r'дет|реб[её]н|семь', 'Расположение':r'располож|центр|мор[ея]|пляж|далек|далёк|близ|локаци'}

def clean(value, limit=600):
    return re.sub(r'<[^>]*>', '', str(value or '')).strip()[:limit]

def cache_path(hid):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,160}',hid): raise ValueError('invalid hotel id')
    return CACHE / (hid+'.json')

def remember(hotel):
    CACHE.mkdir(parents=True,exist_ok=True)
    path=cache_path(hotel['id'])
    if 'content_status' not in hotel:
        old=recall(hotel['id'])
        if old:hotel=dict(old,**hotel)
    payload=json.dumps(hotel,ensure_ascii=False)
    with tempfile.NamedTemporaryFile(mode='w',dir=CACHE,delete=False) as f: f.write(payload); temp=Path(f.name)
    temp.replace(path)

def recall(hid):
    try:
        p=cache_path(hid)
        if p.stat().st_size>300000: return None
        h=json.loads(p.read_text())
        if h.get('id')!=hid or h.get('source_kind')!='public': return None
        return h
    except (OSError,ValueError,TypeError): return None

def valid_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.netloc=='ostrovok.ru' and re.fullmatch(r'/hotel/[a-zA-Z0-9_./-]+/mid[0-9]+/[a-zA-Z0-9_-]+/',p.path) and not p.fragment

async def fetch_page(url):
    if not valid_url(url): raise ToolError('Некорректная ссылка объекта.')
    identity=re.search(r'/mid([0-9]+)/',url).group(1)
    async with httpx.AsyncClient(timeout=7,follow_redirects=False,trust_env=False,headers={'User-Agent':'OPlan-Hackathon/1.0 (public hotel details)','Accept-Language':'ru-RU'}) as client:
        for attempt in range(3):
            async with client.stream('GET',url) as response:
                if response.status_code in {301,302,307,308}:
                    target=urljoin(url,response.headers.get('location',''))
                    if not valid_url(target) or re.search(r'/mid([0-9]+)/',target).group(1)!=identity:raise ValueError('invalid hotel redirect')
                    url=target;continue
                response.raise_for_status();chunks=[];size=0
                async for chunk in response.aiter_bytes():
                    size+=len(chunk)
                    if size>4_000_000:raise ValueError('content too large')
                    chunks.append(chunk)
                return b''.join(chunks).decode('utf-8')
    raise ValueError('hotel redirect limit')

def clock(v):
    if not isinstance(v,dict):return None
    h,m=v.get('hours'),v.get('minutes')
    return f'{h:02}:{m:02}' if type(h)==int and type(m)==int and 0<=h<24 and 0<=m<60 else None

def parse_details(html, base):
    parser=PageData();parser.feed(html)
    data=json.loads(''.join(parser.parts))['props']['pageProps'];h=data['hotel']
    if h.get('id')!=base['id']:raise ValueError('hotel identity mismatch')
    result=deepcopy(base);now=datetime.now(timezone.utc).isoformat();pol=h.get('policies') or {}
    times=(pol.get('checkInCheckOut') or {}).get('value') or {}
    amenities=[clean(a.get('name'),160) for g in h.get('amenityGroups',[]) for a in g.get('amenities',[])]
    rooms=[]
    for room in h.get('roomGroups',[])[:8]:
        n=room.get('nameStruct') or {};name=clean(n.get('mainName'),150)
        if not name:continue
        rooms.append({'name':name,'beds':clean(n.get('beddingType'),100),'area_m2':room.get('size'),'availability':'unknown'})
    charges=[]
    units={'PER_PET_PER_NIGHT':'за питомца за ночь','PER_GUEST_PER_NIGHT':'за гостя за ночь','PER_ROOM_PER_NIGHT':'за номер за ночь','PER_STAY':'за проживание'}
    for key,title in [('pets','Питомцы'),('meal','Питание'),('deposit','Депозит'),('addFee','Доплата'),('cradle','Детская кроватка'),('extraBed','Доп. кровать'),('parking','Парковка'),('shuttle','Трансфер')]:
        values=(pol.get(key) or {}).get('value') or []
        if not isinstance(values,list):continue
        for v in values[:4]:
            price=v.get('price');currency=v.get('currency')
            if isinstance(price,(int,float)) and currency:
                charges.append({'label':title,'price':price,'currency':currency,'unit':units.get(v.get('priceUnit'),'единица оплаты требует уточнения'),'included':v.get('inclusion')=='INCLUDED'})
    extra=clean((pol.get('extraInfo') or {}).get('value'),10000)
    # Only sentences about practical restrictions; no personal names or contacts.
    notes=[s.strip() for s in re.split(r'[\n.!?]+',extra) if re.search(r'бассейн|ограничен|по согласован|залог|питомц|ранн|поздн|доплат|стойк',s,re.I)][:6]
    result['content']={'source_kind':'public','checked_at':now,'room_categories':rooms,'checkin_from':clock(times.get('checkInTimeStart')),'checkin_until':clock(times.get('checkInTimeEnd')),'checkout_until':clock(times.get('checkOutTimeEnd')),'reception_24h':any('Круглосуточная стойка' in a for a in amenities),'policy_notes':notes,'charges':charges,'amenity_groups':[{'name':clean(g.get('name'),80),'items':[clean(a.get('name'),160) for a in g.get('amenities',[])][:100]} for g in h.get('amenityGroups',[])[:12]]}
    result['coordinates']={k:float(h['location'][v]) for k,v in [('lat','latitude'),('lng','longitude')] if isinstance(h.get('location',{}).get(v),(int,float))}
    result['content']['transfer_service']={'listed':any(re.search(r'трансфер|shuttle',a,re.I) for a in amenities),'services':[a for a in amenities if re.search(r'трансфер|shuttle',a,re.I)][:6],'charges':[x for x in charges if x['label']=='Трансфер'],'source_url':base['url'],'checked_at':now,'status':'on_request'}
    result['content_schema']=3
    result['nearby']=[{'name':clean(p.get('name'),120),'distance_m':p.get('distance'),'type':p.get('poiSubtypeSlug')} for p in h.get('location',{}).get('pois',[])[:10] if isinstance(p.get('distance'),(int,float))]
    result['map_points']=[{'name':clean(p.get('name'),100),'lat':p['center']['lat'],'lng':p['center']['lng'],'type':p.get('subtype'),'region_id':p.get('regionId')} for p in data.get('pois',[]) if isinstance(p.get('center'),dict) and isinstance(p['center'].get('lat'),(int,float)) and isinstance(p['center'].get('lng'),(int,float))][:100]
    images=[i.get('tmpl','').replace('{size}','1024x768') for i in h.get('images',[])[:16]]
    images=[u for u in images if urlparse(u).scheme=='https' and urlparse(u).netloc=='cdn.ostrovok.ru']
    if images:result['images']=images;result['image_url']=images[0]
    reviews=[];summary={theme:{'positive_ids':[],'negative_ids':[],'mention_ids':[]} for theme in THEMES}
    # Short excerpts only: aggregate at most 24 source words per page. Theme
    # counts use available source texts, never the total catalogue review count.
    excerpt_words=24
    for r in (data.get('reviews') or {}).get('list',[])[:20]:
        if r.get('reviewType')!='OST':continue
        rid=str(r.get('id',''))
        if not rid or not re.fullmatch(r'[0-9a-zA-Z_-]+',rid):continue
        plus=clean(r.get('reviewPlus'),10000);minus=clean(r.get('reviewMinus'),10000);body=clean(r.get('reviewText'),10000)
        themes=[]
        for theme,pattern in THEMES.items():
            pos=bool(re.search(pattern,plus,re.I));neg=bool(re.search(pattern,minus,re.I));mention=bool(re.search(pattern,body,re.I))
            if pos or neg or mention:themes.append(theme);summary[theme]['mention_ids'].append(rid)
            if pos:summary[theme]['positive_ids'].append(rid)
            if neg:summary[theme]['negative_ids'].append(rid)
        excerpt='';words=(minus or plus or body).split()
        if excerpt_words>0 and words:
            n=min(8,excerpt_words,len(words));excerpt=' '.join(words[:n])+('…' if len(words)>n else '');excerpt_words-=n
        reviews.append({'id':rid,'hotel_id':base['id'],'rating':r.get('rating'),'date':str(r.get('reviewDate',''))[:10],'text':excerpt,'themes':themes,'traveller':{'FAMILY':'Семья','COUPLE':'Пара','SOLO':'Один гость','BUSINESS':'Деловая поездка'}.get(r.get('travellerType'),''),'source_url':base['url'].split('?')[0]+'?language=ru','has_positive':bool(plus),'has_negative':bool(minus) and not re.fullmatch(r'(?:нет|не нашли минусов|минусов нет)[.! ]*',minus,re.I)})
    result.update(review_items=reviews,review_summary=summary,review_checked_at=now,review_sample_size=len(reviews),content_status='loaded',content_checked_at=now)
    result['reviews']=(data.get('reviews') or {}).get('total',result.get('reviews'))
    result['source_kind']='public';return result

async def enrich(hotel):
    old=recall(hotel['id'])
    if old and old.get('content_checked_at'):
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(old['content_checked_at'])).total_seconds()
        if age<21600 and old.get('content_schema')==3:
            result=dict(hotel,**{k:old[k] for k in ['content_schema','content','coordinates','nearby','map_points','images','image_url','review_items','review_summary','review_sample_size','review_checked_at','content_status','content_checked_at'] if k in old});remember(result);return result
    try:result=parse_details(await fetch_page(hotel['url'].split('?')[0]+'?language=ru'),hotel)
    except (httpx.HTTPError,ValueError,KeyError,TypeError,ToolError):
        result=dict(hotel,content_status='unavailable',review_items=[],review_sample_size=0)
        if old and old.get('content_checked_at'):
            result=dict(old,content_status='cached_stale',reference_nightly_minor=hotel.get('reference_nightly_minor'));result['checked_at']=hotel.get('checked_at')
    remember(result);return result
