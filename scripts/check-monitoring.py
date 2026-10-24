import base64,json,urllib.request,urllib.parse
from readiness import wait_for
base='http://localhost:3000'
def get(path, body=None, timeout=15):
 req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(b'admin:admin').decode()})
 with urllib.request.urlopen(req,timeout=timeout) as response: return json.load(response)
wait_for('Grafana health', lambda timeout: get('/api/health',timeout=timeout).get('database') == 'ok')
print('PASS Grafana health')
def datasources_ready(timeout):
 sources=get('/api/datasources',timeout=timeout)
 assert {'prometheus','loki'} <= {s['type'] for s in sources}, 'datasources not provisioned'
 return sources
sources=wait_for('Grafana datasources', datasources_ready)
print('Grafana datasources:',[(s['name'],s['type']) for s in sources])
prom=next(s for s in sources if s['type']=='prometheus')
loki=next(s for s in sources if s['type']=='loki')
def query(source, expression, timeout):
 return get('/api/ds/query', {
  'from': 'now-5m', 'to': 'now',
  'queries': [{'refId':'A','datasource':{'uid':source['uid'],'type':source['type']},
               'expr':expression,'instant':True,'range':False,'maxLines':5,'queryType':'range'}],
 }, timeout=timeout)
def data_ready(source, expression, timeout):
 result=query(source, expression, timeout)
 data=result['results']['A']
 assert not data.get('error'), data['error']
 frames=data.get('frames',[])
 return bool(frames and any(f['data']['values'] and f['data']['values'][-1] for f in frames))
wait_for('application metrics in Prometheus', lambda timeout: data_ready(prom,'http_requests_total',timeout))
print('PASS application metrics in Grafana/Prometheus')
wait_for('Auth logs in Loki', lambda timeout: data_ready(loki,'{service_name="auth"}',timeout))
print('PASS Auth container logs in Grafana/Loki')
