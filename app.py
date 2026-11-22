from flask import Flask, render_template, jsonify, request
from flask_sock import Sock
import os
import uuid
import asyncio
from dotenv import load_dotenv, set_key
from proxy import WebSocketProxy

OFFICIAL_WS = 'wss://api.tenclass.net/xiaozhi/v1/'
RENDER_PROXY_WS = 'wss://onrender.com'

DEFAULT_CONFIG = {
    'WS_URL': OFFICIAL_WS,
    'DEVICE_TOKEN': '123',
    'ENABLE_TOKEN': 'true',
    'LOCAL_PROXY_URL': RENDER_PROXY_WS
}

env_path = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.exists(env_path):
    with open(env_path, 'w') as f:
        for k, v in DEFAULT_CONFIG.items():
            f.write(f"{k}={v}\n")

load_dotenv(env_path)

app = Flask(__name__, static_url_path='/static')
sock = Sock(app)

def get_mac_address():
    mac = uuid.getnode()
    return ':'.join(['{:02x}'.format((mac >> elements) & 0xff) for elements in range(0, 8*6, 8)][::-1])

def get_safe_urls():
    load_dotenv(env_path, override=True)
    ws_url = os.getenv("WS_URL", OFFICIAL_WS)
    local_proxy = os.getenv("LOCAL_PROXY_URL", RENDER_PROXY_WS)
    if "localhost" in ws_url or not ws_url.startswith("ws"):
        ws_url = OFFICIAL_WS
    if "localhost" in local_proxy or local_proxy == "wss://onrender.com":
        local_proxy = RENDER_PROXY_WS
    return ws_url, local_proxy

class SyncToAsyncWS:
    def __init__(self, ws):
        self.ws = ws
        self.remote_address = "render-client"

    async def send(self, data):
        self.ws.send(data)

    def __aiter__(self):
        return self

    async def __anext__(self):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, self.ws.receive)
        if data is None:
            raise StopAsyncIteration
        return data

@sock.route('/ws')
def ws_proxy(ws):
    import proxy as proxy_mod
    ws_url, _ = get_safe_urls()
    proxy_mod.WS_URL = ws_url
    proxy_instance = WebSocketProxy()
    bridge_ws = SyncToAsyncWS(ws)
    asyncio.run(proxy_instance.proxy_handler(bridge_ws))

@app.route('/')
def index():
    ws_url, local_proxy = get_safe_urls()
    return render_template('index.html',
                         device_id=get_mac_address(),
                         token=os.getenv("DEVICE_TOKEN", DEFAULT_CONFIG['DEVICE_TOKEN']),
                         enable_token=os.getenv("ENABLE_TOKEN", "true").lower() == 'true',
                         ws_url=ws_url,
                         local_proxy_url=local_proxy)

@app.route('/save_config', methods=['POST'])
def save_config():
    try:
        data = request.get_json()
        new_ws = data.get('ws_url', OFFICIAL_WS)
        new_proxy = data.get('local_proxy_url', RENDER_PROXY_WS)
        set_key(env_path, 'WS_URL', new_ws)
        set_key(env_path, 'LOCAL_PROXY_URL', new_proxy)
        set_key(env_path, 'DEVICE_TOKEN', data.get('token', ''))
        set_key(env_path, 'ENABLE_TOKEN', str(data.get('enable_token', False)).lower())
        load_dotenv(env_path, override=True)
        return jsonify({'success': True, 'message': '配置已保存'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
