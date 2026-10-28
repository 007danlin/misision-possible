"""Interpret a short amount in the scope of the actual pending question."""
import re
from decimal import Decimal
from .domain import Intent, explicit_ruble_amount


def money_followup(state, message):
    question = state.questions[0] if state.questions else state.assistant_message
    if not re.search(r"сколько.*оставить.*(?:питани|еду|личн|расход)|резерв.*(?:питани|личн|расход)", question, re.I):
        return None
    text = " ".join(message.casefold().replace("ё", "е").split()).rstrip(".! ")
    if re.fullmatch(r"(?:без (?:отдельного )?резерва|ничего(?: не)? (?:оставляем|оставлять)(?: отдельно)?|не (?:нужен|нужно) (?:отдельный )?резерв)", text):
        amount = 0
    else:
        match = re.fullmatch(
            r"(?:(?:оставим|оставь|оставить|резерв(?: на (?:личные|другие) расходы)?)\s+)?"
            r"(?P<value>\d[\d \u00a0]*(?:[.,]\d+)?)"
            r"(?:\s*(?:тыс(?:яч[а-я]*)?\.?|[kк]|млн\.?|миллион[а-я]*)(?:\s*(?:рублей|руб\.?|₽))?|\s*(?:рублей|руб\.?|₽))?"
            r"(?:\s+на (?:еду|питание|личные расходы|еду и личные расходы))?",
            text,
        )
        if not match:
            return None
        amount = explicit_ruble_amount(text)
        if amount is None:
            value = Decimal(match['value'].replace(' ', '').replace('\u00a0', '').replace(',', '.')) * 100
            if value != value.to_integral_value():
                return None
            amount = int(value)
    if not 0 <= amount <= 10**12:
        return None
    return Intent(action='change', patch={'expense_reserve':{'amount_minor':amount}}, evidence={'expense_reserve':message})
