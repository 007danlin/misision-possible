"""Live local Qwen + authoritative Core session lifecycle (synthetic catalogue)."""
import http.cookiejar
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid

base = os.environ.get('TRIP_SMOKE_URL', 'http://127.0.0.1:18080')
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, payload=None, expected=200):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        response = client.open(req, timeout=float(os.environ.get('TRIP_SMOKE_TIMEOUT_SECONDS', '310')))
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = json.load(response)
        assert response.code == expected, (response.code, body)
        return body


def capture(name, snapshot):
    target = os.environ.get('TRIP_SMOKE_EXAMPLES')
    if target:
        folder = Path(target)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ('session-' + name + '.json')).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')


state = request('/api/sessions/', {})
capture('needs-input', state)
path = '/api/sessions/' + state['session_id']


def turn(message):
    global state
    state = request(path + '/turns', {'message': message, 'expected_revision': state['revision'], 'idempotency_key': str(uuid.uuid4())})
    return state


def action(kind, **extra):
    global state
    state = request(path + '/actions', {'type': kind, 'expected_revision': state['revision'], 'idempotency_key': str(uuid.uuid4()), **extra})
    return state


turn('Из Москвы в Сочи, 10–15 ноября 2026, двое взрослых, до 120 тысяч рублей на дорогу, отель и трансферы со сборами, без ночных рейсов.')
assert state['status'] == 'choosing', state
capture('choosing-plans', state)
plan = next(p for p in state['options'] if p['id'].endswith(':A'))
action('select_plan', plan_id=plan['id'])
assert state['selected_plan']['total']['amount_minor'] == 10900000
assert state['checkout_allowed']
capture('ready', state)
turn('Теперь максимум 100 тысяч, остальное оставь')
capture('change-preview', state)
assert state['change_preview']['price_delta'] == -1200000, state
assert state['selected_plan']['id'] == plan['id'] and not state['checkout_allowed']
request(path + '/actions', {'type': 'confirm_booking_demo', 'expected_revision': state['revision'], 'idempotency_key': str(uuid.uuid4())}, expected=409)
turn('Теперь бюджет 30 тысяч рублей, остальное оставь')
assert state['status'] == 'no_solution' and state['change_preview'] is None
assert state['selected_plan']['id'] == plan['id'] and not state['checkout_allowed']
capture('no-solution', state)
request(path + '/actions', {'type': 'accept_change', 'expected_revision': state['revision'], 'idempotency_key': str(uuid.uuid4())}, expected=409)
turn('Вернём бюджет 100 тысяч рублей, остальные условия сохрани')
assert state['change_preview']['price_delta'] == -1200000, state
action('accept_change')
assert state['selected_plan']['total']['amount_minor'] == 9700000
body = {'type': 'confirm_booking_demo', 'expected_revision': state['revision'], 'idempotency_key': str(uuid.uuid4())}
state = request(path + '/actions', body)
repeated = request(path + '/actions', body)
assert state['booking'] == repeated['booking'] and state['revision'] == repeated['revision']
assert state['booking']['is_demo'] and state['status'] == 'booked_demo'
assert request(path)['booking'] == state['booking']
capture('booked-demo', state)
print(json.dumps({'result': 'PASS', 'path': 'UI API → Core → gRPC → local Qwen → tools → persisted demo booking', 'session_id': state['session_id'], 'booking': state['booking']}, ensure_ascii=False, indent=2))

# Each additional direction goes through the catalogue selector and real model,
# not a Sochi branch with a different label.
for destination_id, city, total in [('kazan', 'Казань', 3300000), ('vladimir', 'Владимир', 2300000)]:
    state = request('/api/sessions/', {})
    path = '/api/sessions/' + state['session_id']
    turn('Из Москвы 10–15 ноября 2026, двое взрослых. До 40 тысяч рублей на дорогу, отель, трансферы и сборы. Направление пока не выбрали.')
    assert len(state['destination_options']) >= 3, state
    capture('choosing-destinations', state)
    action('select_destination', destination_id=destination_id)
    assert state['trip_spec']['destination'] == city and state['status'] == 'choosing', state
    selected = next(p for p in state['options'] if p['id'].endswith(':A'))
    action('select_plan', plan_id=selected['id'])
    assert state['selected_plan']['total']['amount_minor'] == total
    action('confirm_booking_demo')
    assert state['booking']['is_demo'] and state['status'] == 'booked_demo'
    print('PASS destination → search → selection → demo booking:', city)
