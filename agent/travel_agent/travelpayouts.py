"""Server-only Aviasales cached direct fares. No live inventory or reservations."""
import os,time
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from zoneinfo import ZoneInfo
import httpx
CITIES={'Москва':'MOW','Сочи':'AER','Санкт-Петербург':'LED','Казань':'KZN'}
SOURCE='https://travelpayouts.github.io/slate/#non-stop-tickets'
_cache={}

def key(spec):return '|'.join([spec.origin or '',spec.destination or '',str(spec.dates.start) if spec.dates else '',str(spec.dates.end) if spec.dates else ''])
def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))
def parse(data,spec,now=None):
    now=now or datetime.now(timezone.utc);rows=(data.get('data') or {}).get(CITIES.get(spec.destination),{})
    if not data.get('success') or not isinstance(rows,dict):return None
    valid=[]
    for row in rows.values():
        try:
            out=timestamp(row['departure_at']);back=timestamp(row['return_at']);expires=timestamp(row['expires_at'])
            if any(d.tzinfo is None for d in (out,back,expires)) or expires<=now or out<=now or back<=out:continue
            out=out.astimezone(ZoneInfo('Europe/Moscow'));back=back.astimezone(ZoneInfo('Europe/Moscow'))
            if out.date()!=spec.dates.start or back.date()!=spec.dates.end:continue
            price=int(Decimal(str(row['price']))*100);mins=row.get('duration_to');return_mins=row.get('duration_back')
            if price<=0 or price>100000000 or type(mins)!=int or type(return_mins)!=int or not 1<=mins<=1440 or not 1<=return_mins<=1440:continue
            valid.append({'roundtrip_minor':price,'departure':out.isoformat(),'return_departure':back.isoformat(),'minutes':mins,'return_minutes':return_mins,'expires_at':expires.isoformat(),'airline':str(row.get('airline',''))[:8],'source':'Aviasales / Travelpayouts · кэш прямых перелётов','source_url':SOURCE,'retrieved':time.time(),'dates':{'start':str(spec.dates.start),'end':str(spec.dates.end)}})
        except (KeyError,ValueError,TypeError,InvalidOperation):continue
    return min(valid,key=lambda r:r['roundtrip_minor']) if valid else None

def valid_for(reference,spec):
    try:return reference.get('dates')=={'start':str(spec.dates.start),'end':str(spec.dates.end)} and timestamp(reference['expires_at'])>datetime.now(timezone.utc) and time.time()-reference['retrieved']<1800
    except (KeyError,TypeError,ValueError):return False

async def prepare(spec):
    token=os.getenv('TRAVELPAYOUTS_TOKEN','').strip()
    if not token or not spec.dates or spec.origin not in CITIES or spec.destination not in CITIES or spec.origin==spec.destination or spec.transport_owned:return None
    old=_cache.get(key(spec))
    if old and time.time()-old['at']<300 and (old['value'] is None or valid_for(old['value'],spec)):return old['value']
    try:
        async with httpx.AsyncClient(timeout=4,headers={'X-Access-Token':token,'User-Agent':'OPlan-Hackathon/1.0'}) as client:
            # Token is deliberately never in query parameters, snapshots or logs.
            r=await client.get('https://api.travelpayouts.com/v1/prices/direct',params={'origin':CITIES[spec.origin],'destination':CITIES[spec.destination],'depart_date':str(spec.dates.start),'return_date':str(spec.dates.end),'currency':'RUB'});r.raise_for_status()
            if len(r.content)>500000:return None
            result=parse(r.json(),spec);_cache[key(spec)]={'at':time.time(),'value':result};return result
    except (httpx.HTTPError,ValueError,TypeError):return None
