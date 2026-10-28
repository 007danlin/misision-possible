"""Unambiguous calendar replies, independent of model size and destination.

Keep a lone check-in date until a length is known. Complex/conditional messages
remain with the language model; never infer a date from a month or duration alone.
"""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .domain import Intent
from .fast_intent import COUNT, number

MONTHS = "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split()
DATE = (
    r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}(?:[./]\d{4})?|"
    r"\d{1,2}\s+(?:" + "|".join(MONTHS) + r")(?:\s+\d{4}(?:\s+года)?)?|послезавтра|завтра|сегодня)"
)


def calendar_followup(message, today=None):
    text = message.strip().lower().replace("ё", "е").rstrip(".! ")
    match = re.fullmatch(
        r"(?:(?:давай|давайте|поедем|едем|перенеси|перенесем|начнем)\s+)?"
        r"(?:(?:на|с|заезд(?:\s+с)?|начиная с)\s+)?(?P<start>" + DATE + r")"
        r"(?:\s*,?\s*на\s+(?P<count>" + COUNT + r")\s+(?P<unit>ночь|ночи|ночей|день|дня|дней))?",
        text,
    )
    if not match:
        return None
    today = today or datetime.now(ZoneInfo("Europe/Moscow")).date()
    raw = match["start"]
    try:
        if raw in {"сегодня", "завтра", "послезавтра"}:
            start = today + timedelta(days={"сегодня": 0, "завтра": 1, "послезавтра": 2}[raw])
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            start = date.fromisoformat(raw)
        else:
            parts = re.split(r"[./\s]+", raw)
            day = int(parts[0])
            month = MONTHS.index(parts[1]) + 1 if parts[1] in MONTHS else int(parts[1])
            explicit_year = len(parts) >= 3
            year = int(parts[2]) if explicit_year else today.year
            # Choose the next valid occurrence, including February 29.
            for candidate in range(year, year + (1 if explicit_year else 9)):
                try:
                    start = date(candidate, month, day)
                except ValueError:
                    continue
                if explicit_year or start >= today:
                    break
            else:
                raise ValueError("invalid calendar date")
        if start < today:
            return Intent(action="clarify", questions=["Эта дата уже прошла. На какую будущую дату перенести поездку?"])
    except ValueError:
        return Intent(action="clarify", questions=["Такой даты в календаре нет. Уточните дату заезда, пожалуйста."])
    patch = {"checkin_date": start.isoformat()}
    if match["count"]:
        count = number(match["count"])
        field = "stay_nights" if match["unit"].startswith("ноч") else "duration_days"
        if not 1 <= count <= (60 if field == "stay_nights" else 365):
            return Intent(action="clarify", questions=["Уточните длительность поездки, пожалуйста."])
        patch[field] = count
    return Intent(patch=patch, evidence={key: message for key in patch}, action="change")
