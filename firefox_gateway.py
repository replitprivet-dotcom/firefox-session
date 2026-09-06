import os, re, secrets, time, json, subprocess
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from urllib.parse import parse_qs

app = FastAPI(title='Firefox Session Gateway')
STATE = Path('/data/sessions.json')
BASE_PORT = 6100
PUBLIC_IP = os.getenv('PUBLIC_IP', '172.232.172.170')
ADMIN_KEY = os.getenv('ADMIN_KEY', 'maha7788')
IMAGE = 'jlesage/firefox:latest'

def load():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def save(x):
    STATE.parent.mkdir(parents=True, exist_ok=True); STATE.write_text(json.dumps(x, indent=2))

def valid_id(x): return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,48}', x or ''))

def docker(*args):
    p=subprocess.run(['docker',*args], text=True, capture_output=True)
    if p.returncode: raise HTTPException(500, p.stderr.strip() or 'docker command failed')
    return p.stdout.strip()

def require_key(key: str):
    if not secrets.compare_digest(key, ADMIN_KEY):
        raise HTTPException(403, 'invalid admin key')


def next_port(s):
    used={v['port'] for v in s.values()}
    for p in range(BASE_PORT, BASE_PORT+1000):
        if p not in used: return p
    raise HTTPException(503,'No free Firefox ports')

@app.get('/adduser')
def adduser(password: str, day: int=7, id: str='', key: str=''):
    require_key(key)
    if not valid_id(id): raise HTTPException(400,'id must contain only letters, numbers, _ or -')
    if not 1 <= day <= 365: raise HTTPException(400,'day must be 1..365')
    if len(password) < 4 or len(password) > 8: raise HTTPException(400,'VNC password must be 4..8 characters')
    s=load(); old=s.get(id)
    if old: raise HTTPException(409,'id already exists; use /delete first')
    port=next_port(s); token=secrets.token_urlsafe(18); expires=int(time.time())+day*86400
    name='fx-'+id
    docker('run','-d','--name',name,'--restart','unless-stopped','-p',f'{port}:5800','-p',f'{port+1000}:5900','-e',f'VNC_PASSWORD={password}','-e','WEB_HOST_CLIPBOARD_SYNC=0','-e','KEEP_APP_RUNNING=1','-e','DISPLAY_WIDTH=1280','-e','DISPLAY_HEIGHT=800','-v',f'fx_{id}_config:/config',IMAGE)
    s[id]={'token':token,'port':port,'vnc_port':port+1000,'expires':expires,'container':name,'password':password}; save(s)
    link=f'http://{PUBLIC_IP}:6080/kaalix/firefoxwep__/{id}-{token}?host={PUBLIC_IP}&port={port}&path=websockify&autoconnect=true&resize=scale&noclipboard=1'
    return {'ok':True,'id':id,'expires_at':expires,'link':link,'vnc':f'{PUBLIC_IP}:{port+1000}'}

@app.get('/delete')
def delete(id: str, password: str, key: str=''):
    require_key(key)
    s=load(); x=s.get(id)
    if not x or x['password'] != password: raise HTTPException(404,'invalid id or password')
    docker('rm','-f',x['container']); docker('volume','rm',f'fx_{id}_config')
    del s[id]; save(s); return {'ok':True,'deleted':id}

@app.get('/newpas')
def newpas(id: str, password: str, newpassword: str, key: str=''):
    require_key(key)
    s=load(); x=s.get(id)
    if not x or x['password'] != password: raise HTTPException(404,'invalid id or password')
    if len(newpassword)<4 or len(newpassword)>8: raise HTTPException(400,'newpassword must be 4..8 characters')
    docker('rm','-f',x['container']); port=x['port']; name=x['container']
    docker('run','-d','--name',name,'--restart','unless-stopped','-p',f'{port}:5800','-p',f'{port+1000}:5900','-e',f'VNC_PASSWORD={newpassword}','-e','WEB_HOST_CLIPBOARD_SYNC=0','-e','KEEP_APP_RUNNING=1','-e','DISPLAY_WIDTH=1280','-e','DISPLAY_HEIGHT=800','-v',f'fx_{id}_config:/config',IMAGE)
    x['password']=newpassword; s[id]=x; save(s); return {'ok':True,'id':id,'password_changed':True}

@app.get('/kaalix/firefoxwep__/{slug}')
def session_link(slug: str, host: str='', port: int=0, path: str='websockify', autoconnect: str='true', resize: str='scale', noclipboard: str='1'):
    s = load()
    item = next((v for sid, v in s.items() if f'{sid}-{v.get("token", "")}' == slug), None)
    if not item or item['expires'] < int(time.time()):
        raise HTTPException(404, 'link expired or invalid')
    target = f'http://{PUBLIC_IP}:{item["port"]}/?host={PUBLIC_IP}&port={item["port"]}&path=websockify&autoconnect=true&resize=scale&noclipboard=1'
    return RedirectResponse(target, status_code=302)

@app.get('/')
def root():
    return HTMLResponse('''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Firefox Login</title><style>body{font-family:Arial;background:#f2f4f7;display:grid;place-items:center;height:100vh;margin:0}.box{background:white;padding:28px;border-radius:12px;box-shadow:0 4px 20px #0002;width:min(360px,85vw)}h2{margin-top:0}input,button{box-sizing:border-box;width:100%;padding:12px;margin:7px 0;border:1px solid #ccd2d9;border-radius:7px;font-size:16px}button{background:#1769e0;color:white;border:0;cursor:pointer}</style></head><body><div class="box"><h2>Firefox Login</h2><form method="post" action="/login"><input name="username" placeholder="Username / ID" autocomplete="username" required><input name="password" type="password" placeholder="Password" autocomplete="current-password" required><button type="submit">Login</button></form></div></body></html>''')


@app.post('/login')
async def login(request: Request):
    data = parse_qs((await request.body()).decode('utf-8'))
    username = data.get('username', [''])[0]
    password = data.get('password', [''])[0]
    s = load(); item = s.get(username)
    if not item or item.get('password') != password or item.get('expires', 0) < int(time.time()):
        return HTMLResponse('<p>Invalid username or password. <a href="/">Try again</a></p>', status_code=401)
    target = f'http://{PUBLIC_IP}:{item["port"]}/?host={PUBLIC_IP}&port={item["port"]}&path=websockify&autoconnect=true&resize=scale&noclipboard=1'
    return RedirectResponse(target, status_code=303)


@app.get('/health')
def health(): return {'ok':True,'sessions':len(load())}
