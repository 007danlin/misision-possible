"""Compare downloaded PDF text with confirmed bookings and check page geometry."""
import argparse,json,re,unicodedata
from pathlib import Path
import pdfplumber

parser=argparse.ArgumentParser();parser.add_argument('--dir',type=Path,default=Path('.runtime/screenshots/pdf-booking'));parser.add_argument('--render',action='store_true');args=parser.parse_args()
def compact(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(value)))
def price(n):
 n=int(n);return f'{n//100:,}'.replace(',',' ')+(f',{n%100:02d}' if n%100 else '')+' ₽'
def count(n,one,few,many):return f'{n} '+(many if 11<=n%100<=14 else one if n%10==1 else few if 2<=n%10<=4 else many)
months=['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря']
headings={'ВАШ ТАРИФ','ПОЧЕМУ ЭТОТ ОТЕЛЬ','Состав стоимости','Дорога и трансферы · время МСК','Проверка плана','Дополнительно: оба трансфера','Пожелание раннего заезда','Перед поездкой'}
results=[]
for record in json.loads((args.dir/'report.json').read_text()):
 path=args.dir/record['file'];b=record['booking'];h=b['hotel'];q=b.get('quote') or h['quote'];j=h.get('journey');addon=h.get('transfer_addon');errors=[]
 with pdfplumber.open(path) as pdf:
  full='\n'.join(p.extract_text() or '' for p in pdf.pages);flat=compact(full)
  def contains(value,label):
   if compact(value) not in flat:errors.append(f'missing {label}: {value}')
  contains(h['name'],'hotel');contains(h['address'],'address');contains(b['guest_name'],'guest name');contains(b['id'],'booking id')
  for key in ['start','end']:
   year,month,day=map(int,b['dates'][key].split('-'));contains(f'{day} {months[month-1]} {year}',key)
  travellers=b['travellers'];contains(count(travellers['adults'],'взрослый','взрослых','взрослых'),'adults')
  children=travellers.get('children') or []
  if children:
   contains(count(len(children),'ребёнок','ребёнка','детей'),'children count')
   contains('Возраст детей: '+', '.join('не указан' if a is None else 'до 1 года' if a==0 else count(a,'год','года','лет') for a in children),'child ages')
  total=(j['total_minor'] if j else h['quote']['total_minor'])+(addon['total_minor'] if addon else 0)
  contains(price(total),'confirmed total');contains(price(q['nightly_minor'])+' / ночь','nightly price')
  if j:
   if j.get('total_incomplete'):contains('ПЛАН БЕЗ СТОИМОСТИ ВАШИХ БИЛЕТОВ','incomplete cost label')
   assert j['total_minor']==sum(j['breakdown'].values()),'invalid saved journey'
   for segment in j['segments']:
    for field in ['origin','destination','label']:contains(segment[field],field)
    for field in (['arrival'] if segment.get('time_partial')=='arrival' else ['departure'] if segment.get('time_partial')=='departure' else ['arrival','departure']):contains(segment[field][11:16],field+' time')
   for n in j['breakdown'].values():contains(price(n),'breakdown')
  if addon:
   contains(price(addon['total_minor']),'transfer addition')
   for segment in addon['segments']:
    contains(segment['origin'],'transfer origin');contains(segment['destination'],'transfer destination');contains(segment['departure'][11:16],'transfer departure');contains(segment['arrival'][11:16],'transfer arrival')
  for index,p in enumerate(pdf.pages):
   contains(f'{index+1} / {len(pdf.pages)}','page numbering')
   for c in p.chars:
    if c['x0']<35 or c['x1']>p.width-35 or c['top']<24 or c['bottom']>p.height-23:errors.append(f'page {index+1}: character outside margins {c["text"]!r}');break
   words=p.extract_words();overlaps=[]
   for k,a in enumerate(words):
    for v in words[k+1:]:
     dx=min(a['x1'],v['x1'])-max(a['x0'],v['x0']);dy=min(a['bottom'],v['bottom'])-max(a['top'],v['top'])
     if dx>2 and dy>min(a['bottom']-a['top'],v['bottom']-v['top'])*.6:overlaps.append((a['text'],v['text']))
   if overlaps:errors.append(f'page {index+1}: overlapping words {overlaps[:3]}')
   lines=[line for line in p.extract_text_lines() if 75<line['top']<790]
   if lines and lines[-1]['text'].strip() in headings:errors.append(f'page {index+1}: orphan heading {lines[-1]["text"]}')
  results.append({'file':record['file'],'pages':len(pdf.pages),'total_minor':total,'passed':not errors,'errors':errors})
 if args.render:
  import pypdfium2 as pdfium
  render=args.dir/'rendered';render.mkdir(exist_ok=True);doc=pdfium.PdfDocument(path)
  for i in range(len(doc)):
   page=doc[i];bitmap=page.render(scale=1.4);bitmap.to_pil().save(render/f'{path.stem}-{i+1}.png');bitmap.close();page.close()
  doc.close()
 print(('PASS' if not errors else 'FAIL'),record['file'],*errors,sep='\n  ')
(args.dir/'validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
raise SystemExit(0 if all(r['passed'] for r in results) else 1)
