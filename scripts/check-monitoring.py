import base64,json,urllib.request,urllib.parse
base='http://localhost:3000'
def get(path, body=None):
 req=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Basic '+base64.b64encode(b'admin:admin').decode()})
 with urllib.request.urlopen(req,timeout=15) as response: return json.load(response)
health=get('/api/health');assert health['database']=='ok';print('PASS Grafana health')
sources=get('/api/datasources')
print('Grafana datasources:',[(s['name'],s['type']) for s in sources])
prom=next(s for s in sources if s['type']=='prometheus')
loki=next(s for s in sources if s['type']=='loki')
def query(source, expression):
 return get('/api/ds/query', {
  'from': 'now-5m', 'to': 'now',
  'queries': [{'refId':'A','datasource':{'uid':source['uid'],'type':source['type']},
               'expr':expression,'instant':True,'range':False,'maxLines':5,'queryType':'range'}],
 })
metrics=query(prom,'http_requests_total')
frames=metrics['results']['A'].get('frames',[])
assert frames and any(f['data']['values'] and f['data']['values'][-1] for f in frames),metrics
print('PASS application metrics in Grafana/Prometheus')
logs=query(loki,'{service_name="auth"}')
frames=logs['results']['A'].get('frames',[])
assert frames and any(f['data']['values'] and f['data']['values'][-1] for f in frames),logs
print('PASS Auth container logs in Grafana/Loki')
