"""Small preference-aware selection from the hotel's real public POI data."""
import re
from .trip_context import distance

def nearby_places(hotel,spec):
    origin=hotel.get('coordinates') or {};points={p['name']:dict(p) for p in hotel.get('map_points',[])}
    for p in hotel.get('nearby',[]):points[p['name']]=dict(points.get(p['name'],{}),**p)
    result=[];wishes=' '.join(spec.preferences).lower();family=bool(spec.travellers.children);nature=spec.travel_setting in {'nature','forest','mountains'} or bool(re.search(r'природ|спокой|тишин',wishes));sea=spec.travel_setting=='sea' or spec.hotel_preferences.max_beach_m is not None
    for p in points.values():
        name=p['name'];kind=p.get('type') or ''
        if re.search('аэропорт|вокзал',name,re.I):continue
        coords=all(isinstance(p.get(k),(float,int)) for k in ['lat','lng'])
        km=distance((origin['lat'],origin['lng']),(p['lat'],p['lng'])) if coords and 'lat' in origin else p.get('distance_m',1e9)/1000
        if km>30:continue
        if re.search('пляж|BEACH',name+' '+kind,re.I):category='Море';reason='Место для прогулки у воды; условия купания зависят от сезона.';score=3 if sea else 0
        elif re.search('парк|сад|дендрар|озер|озёр|лес|PARK',name+' '+kind,re.I):category='Прогулки';reason='Природная точка для прогулки; доступность троп нужно уточнить.';score=3 if nature else 2 if family else 1
        elif re.search('океанари|зоопарк|дельфинар|аквапарк',name,re.I):category='С детьми';reason='Можно рассмотреть для семейного досуга; часы работы и билеты уточняются.';score=4 if family else 1
        elif re.search('музей|театр|собор|храм|башн|кремль|MUSEUM|MONUMENT',name+' '+kind,re.I):category='Впечатления';reason='Местная достопримечательность для прогулочной программы.';score=1
        else:category='Рядом';reason='Ориентир из публичной карточки отеля.';score=0
        p.update(category=category,reason=reason,distance_m=round(km*1000),distance_kind='straight' if coords else 'source',source_url=hotel.get('url'),score=score-km/10)
        result.append(p)
    result.sort(key=lambda p:(-p['score'],p['distance_m']))
    return result[:5]
