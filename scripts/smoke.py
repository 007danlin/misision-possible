import base64, hashlib, hmac, json, os, struct, subprocess, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1])
base=os.environ.get('SMOKE_BASE_URL','http://localhost')
compose=['docker','compose','-f','infra/docker-compose.dev.yml']
def command(*args):
 return subprocess.check_output(compose+list(args),text=True).strip()
def request(path,data=None,token=None,status=200):
 headers={'Content-Type':'application/json'}
 if token: headers['Authorization']='Bearer '+token
 req=urllib.request.Request(base+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=15) as resp: actual=resp.status;body=resp.read()
 except urllib.error.HTTPError as exc:actual=exc.code;body=exc.read()
 assert actual in (status if isinstance(status,tuple) else (status,)),(path,actual,body.decode())
 return json.loads(body) if body else {}
# Never send test verification codes to external addresses.
assert command('exec','-T','notif','sh','-c','if [ -n "$SMTP_USER" ]; then echo configured; else echo stub; fi') == 'stub', 'Smoke check requires SMTP stub mode'
username='smoke_' +str(int(time.time()))
email=username+'@gmail.com'
password='Test123!'
created=request('/api/auth/auth/register',{'username':username,'email':email,'password':password},status=201)
uid=created['user_id'];print('PASS registration, users schema')
code=command('exec','-T','redis','redis-cli','GET','verify:'+uid)
pair=request('/api/auth/auth/verify-email',{'user_id':uid,'code':code});token=pair['access_token']
print('PASS email verification and token issue')
profile=request('/api/auth/users/me',token=token);assert profile['status']=='active';print('PASS authenticated profile')
request('/api/core/handle',{'name':'Alice'},token='demo-admin',status=401)
request('/api/core/handle',{'name':'Alice'},status=401);print('PASS missing/forged bearer rejected')
result=request('/api/core/handle',{'name':'Alice'},token=token)
assert result['caller']==uid and result['agent_message']=='hello Alice from agent',result
print('PASS Core -> Auth -> Agent via gRPC',result)
newmail=username+'@yandex.ru'
request('/api/auth/users/me/change-email',{'new_email':newmail},token=token)
pending=json.loads(command('exec','-T','redis','redis-cli','GET','changeemail:'+uid))
request('/api/auth/users/me/change-email/confirm',{'code':pending['code']},token=token)
assert request('/api/auth/users/me',token=token)['email']==newmail
print('PASS email change')
# Verify NATS subscriber processed both verification and email-change events.
logs=command('logs','--no-color','notif')
assert email in logs and 'auth.user.email_change_requested' in logs and newmail in logs
print('PASS NATS notifications for registration and email change (SMTP stub)')
request('/api/auth/auth/logout',{},token=token)
request('/api/core/handle',{'name':'Alice'},token=token,status=401);print('PASS revoked token rejected by Core')
pair=request('/api/auth/auth/login',{'email':newmail,'password':password})
fresh=request('/api/auth/auth/refresh',{'refresh_token':pair['refresh_token']})
request('/api/auth/auth/refresh',{'refresh_token':pair['refresh_token']},status=401)
# Only one service instance may consume the same refresh token.
with ThreadPoolExecutor(max_workers=6) as pool:
 results=list(pool.map(lambda _:request('/api/auth/auth/refresh',{'refresh_token':fresh['refresh_token']},status=(200,401)),range(6)))
successes=[result for result in results if 'access_token' in result]
assert len(successes)==1, 'refresh token was consumed more than once'
fresh=successes[0]
print('PASS concurrent refresh token consumption')
request('/api/core/handle',{'name':'Alice'},token=fresh['access_token'])
request('/api/auth/auth/logout-all',{},token=fresh['access_token'])
request('/api/core/handle',{'name':'Alice'},token=fresh['access_token'],status=401)
print('PASS login, refresh rotation, logout-all')
pair=request('/api/auth/auth/login',{'email':newmail,'password':password})
token=pair['access_token']
secret=request('/api/auth/users/me/2fa/enable',{},token=token)['secret']
def totp():
 key=base64.b32decode(secret+'='*((-len(secret))%8))
 digest=hmac.new(key,struct.pack('>Q',int(time.time())//30),hashlib.sha1).digest()
 offset=digest[-1]&15
 return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
request('/api/auth/users/me/2fa/confirm',{'code':totp()},token=token)
pending=request('/api/auth/auth/login',{'email':newmail,'password':password})
assert pending['requires_2fa'] is True
wrong=str((int(totp())+1)%1000000).zfill(6)
request('/api/auth/auth/2fa/verify',{'pending_token':pending['pending_token'],'code':wrong},status=401)
pair=request('/api/auth/auth/2fa/verify',{'pending_token':pending['pending_token'],'code':totp()})
request('/api/core/handle',{'name':'Alice'},token=pair['access_token'])
request('/api/auth/users/me/2fa/disable',{'password':password,'code':totp()},token=pair['access_token'])
request('/api/auth/auth/logout-all',{},token=pair['access_token'])
print('PASS 2FA setup, login challenge, invalid code rejection, disable')

print('ALL APPLICATION SMOKE CHECKS PASSED; test user:',uid)
