from flask import Flask, render_template, jsonify, request
from flask_sock import Sock
import os
import uuid
import asyncio
import threading
import websockets
from dotenv import load_dotenv, set_key
from proxy import WebSocketProxy

DEFAULT_CONFIG = {
    'WS_URL': 'wss://api.tenclass.net/xiaozhi/v1/',
    'DEVICE_TOKEN': '123',
    'ENABLE_TOKEN': 'true',
    'LOCAL_PROXY_URL': 'wss://://onrender.com'
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

class SyncToAsyncWS:
    """將 flask-sock 同步連線橋接給原本的 async proxy"""
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
    load_dotenv(env_path, override=True)
    import proxy as proxy_mod
    proxy_mod.WS_URL = os.getenv("WS_URL", DEFAULT_CONFIG['WS_URL'])
    proxy_instance = WebSocketProxy()
    bridge_ws = SyncToAsyncWS(ws)
    asyncio.run(proxy_instance.proxy_handler(bridge_ws))

@app.route('/')
def index():
    load_dotenv(env_path, override=True)
    return render_template('index.html',
                         device_id=get_mac_address(),
                         token=os.getenv("DEVICE_TOKEN", DEFAULT_CONFIG['DEVICE_TOKEN']),
                         enable_token=os.getenv("ENABLE_TOKEN", "true").lower() == 'true',
                         ws_url=os.getenv("WS_URL", DEFAULT_CONFIG['WS_URL']),
                         local_proxy_url=os.getenv("LOCAL_PROXY_URL", DEFAULT_CONFIG['LOCAL_PROXY_URL']))

@app.route('/save_config', methods=['POST'])
def save_config():
    try:
        data = request.get_json()
        set_key(env_path, 'WS_URL', data.get('ws_url', DEFAULT_CONFIG['WS_URL']))
        set_key(env_path, 'LOCAL_PROXY_URL', data.get('local_proxy_url', DEFAULT_CONFIG['LOCAL_PROXY_URL']))
        set_key(env_path, 'DEVICE_TOKEN', data.get('token', ''))
        set_key(env_path, 'ENABLE_TOKEN', str(data.get('enable_token', False)).lower())
        load_dotenv(env_path, override=True)
        return jsonify({'success': True, 'message': '配置已保存'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=False)
