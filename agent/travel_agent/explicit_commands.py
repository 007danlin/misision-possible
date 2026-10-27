"""Complete, bounded grammar for explicit edits; unknown text always goes to Qwen."""
import re
from .domain import Intent, explicit_ruble_amount

AMENITIES={
 'бассейн':'pool','бассейна':'pool', 'парковка':'parking','парковку':'parking','парковки':'parking',
 'завтрак':'breakfast','завтраки':'breakfast','завтрака':'breakfast', 'спа':'spa',
 'фитнес':'fitness','спортзал':'fitness','тренажерный зал':'fitness',
}


def explicit_commands(state,message):
    text=' '.join(message.strip().lower().replace('ё','е').split()).rstrip('.!?')
    if '?' in message or len(message)>500 or re.search(r'\b(?:если|или|либо|кроме|вместо)\b',text):return None
    # Decimal commas stay inside a price. Every other clause must be understood.
    clauses=re.split(r'(?<!\d)[,;.]\s*|[,;.]\s*(?!\d)|\s+(?:но|зато)\s+',text)
    patch={};removed=[];changed=set();operations=0
    for clause in clauses:
        clause=re.sub(r'^(?:а|но|зато|и)\s+','',clause).strip()
        if not clause:continue
        if re.fullmatch(r'(?:остальное|остальные (?:условия|пожелания)) (?:оставь|сохрани|прежние|не меняй)|(?:оставь|сохрани) (?:остальное|остальные (?:условия|пожелания))',clause):continue
        mode=None;names=None
        m=re.fullmatch(r'(?:добавь|нужен|нужна|нужно|нужны|хочу) (.+)',clause)
        if m:mode=True;names=m[1]
        m=re.fullmatch(r'(?:убери|сними требование(?: на)?) (.+)',clause)
        if m:mode='remove';names=m[1]
        m=re.fullmatch(r'(.+?) (?:больше )?(?:не (?:обязателен|обязательна|обязательны|важен|важна|важны)|необязателен|необязательна)',clause)
        if m:mode='remove';names=m[1]
        m=re.fullmatch(r'(.+?) (?:обязателен|обязательна|обязательны|нужен|нужна|нужны)',clause)
        if m and mode is None:mode=True;names=m[1]
        if mode is not None:
            parts=re.split(r'\s+и\s+',names)
            if not parts or any(n not in AMENITIES for n in parts):return None
            keys=[AMENITIES[n] for n in parts]
            if any(key in changed for key in keys):return None
            changed.update(keys)
            for key in keys:
                if mode=='remove':removed.append(key)
                else:patch.setdefault('hotel_preferences',{})[key]=mode
            operations+=1;continue
        m=re.fullmatch(r'(?:(?:бюджет(?: (?:снизим|увеличим|уменьшим))?|(?:снизь|уменьши|увеличь) бюджет)\s+)?(?:до\s+)?(\d[\d ]*(?:[.,]\d+)?\s*(?:тысяч(?:и)?|тыс\.?|рублей|руб|₽)(?:\s+рублей)?)(?:\s+(на (?:отель|все проживание)|за (?:все проживание|весь отдых|ночь)|в сутки))?',clause)
        if m:
            if 'budget' in changed:return None
            amount=explicit_ruble_amount(m[1])
            if amount is None:return None
            patch['budget']={'amount_minor':amount};changed.add('budget')
            scope=m[2] or ''
            if scope in {'за ночь','в сутки'}:patch['budget_period']='night'
            elif scope in {'на все проживание','за все проживание','за весь отдых'}:patch['budget_period']='stay'
            if 'отель' in scope or 'проживание' in scope:patch['budget_scope']='hotel'
            operations+=1;continue
        # Do not interpret any residual prose, negation, question or preference.
        return None
    if not operations:return None
    evidence={key:message for key in patch}
    if removed:evidence['remove_hotel_preferences']=message
    return Intent(patch=patch,remove_hotel_preferences=removed,evidence=evidence,action='change')
