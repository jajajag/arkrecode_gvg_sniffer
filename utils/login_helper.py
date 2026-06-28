import base64
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse
from urllib.request import urlopen


LOGIN_URL = 'https://sadpki-portal.ebuajk.com/api/v2/login'
LOGIN_PAGE = (
    'https://sadpki-portal.ebuajk.com/login/?merchantId=&serviceId='
    '&callback=coresdk://coresdk.games/com.nerversoft.ark.recode'
    '&login=true&game_id=32&lang=en&platform=R18'
)


class DevToolsWebSocket:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.sock = None
        self.next_id = 1

    def __enter__(self):
        parsed = urlparse(self.ws_url)
        port = parsed.port or 80
        path = parsed.path
        if parsed.query:
            path += '?' + parsed.query

        self.sock = socket.create_connection((parsed.hostname, port), timeout=10)
        key = base64.b64encode(secrets.token_bytes(16)).decode('ascii')
        request = (
            f'GET {path} HTTP/1.1\r\n'
            f'Host: {parsed.hostname}:{port}\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            f'Sec-WebSocket-Key: {key}\r\n'
            'Sec-WebSocket-Version: 13\r\n'
            '\r\n'
        )
        self.sock.sendall(request.encode('ascii'))
        response = self._recv_until(b'\r\n\r\n')
        if b' 101 ' not in response.split(b'\r\n', 1)[0]:
            raise RuntimeError(f'WebSocket handshake failed: {response!r}')
        self.sock.settimeout(1)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            self.sock.close()

    def _recv_until(self, marker):
        data = b''
        while marker not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _recv_exact(self, size):
        data = b''
        while len(data) < size:
            chunk = self.sock.recv(size - len(data))
            if not chunk:
                raise ConnectionError('WebSocket closed')
            data += chunk
        return data

    def _send_frame(self, opcode, payload):
        header = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack('!H', length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack('!Q', length))

        mask = secrets.token_bytes(4)
        masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def send_json(self, payload):
        raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        self._send_frame(0x1, raw)

    def recv_json(self):
        while True:
            first, second = self._recv_exact(2)
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack('!H', self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack('!Q', self._recv_exact(8))[0]

            mask = self._recv_exact(4) if masked else b''
            payload = self._recv_exact(length) if length else b''
            if masked:
                payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))

            if opcode == 0x8:
                raise ConnectionError('WebSocket closed by browser')
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0x1:
                return json.loads(payload.decode('utf-8'))

    def command(self, method, params=None):
        msg_id = self.next_id
        self.next_id += 1
        payload = {'id': msg_id, 'method': method}
        if params is not None:
            payload['params'] = params
        self.send_json(payload)
        return msg_id


def find_browser():
    roots = [
        os.environ.get('PROGRAMFILES'),
        os.environ.get('PROGRAMFILES(X86)'),
        os.environ.get('LOCALAPPDATA'),
    ]
    for root in roots:
        if not root:
            continue
        for path in (
            Path(root) / 'Google' / 'Chrome' / 'Application' / 'chrome.exe',
            Path(root) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe',
        ):
            if path.exists():
                return path
    return None


def wait_for_devtools(port, timeout=10):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f'浏览器调试端口未启动：{last_error}')


def get_devtools_page(port):
    with urlopen(f'http://127.0.0.1:{port}/json/list', timeout=5) as resp:
        pages = json.loads(resp.read().decode('utf-8'))
    for page in pages:
        if page.get('type') == 'page' and page.get('webSocketDebuggerUrl'):
            return page
    raise RuntimeError('没有找到可用的浏览器页面')


def parse_cdp_body(body_result):
    body = body_result.get('body', '')
    if body_result.get('base64Encoded'):
        body = base64.b64decode(body).decode('utf-8', errors='replace')
    return json.loads(body)


def extract_login_payload(data):
    payload = data.get('data') if isinstance(data, dict) else None
    if not isinstance(payload, dict) or not payload.get('jwt'):
        raise RuntimeError(
            '登录响应里没有 jwt：\n' + json.dumps(data, ensure_ascii=False, indent=2)
        )
    return payload


def capture_login(timeout=300):
    browser_path = find_browser()
    if not browser_path:
        raise RuntimeError('没有找到 Chrome 或 Edge')

    port = 9223
    profile_dir = Path(tempfile.gettempdir()) / 'erolabs_login_helper_profile'
    profile_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            str(browser_path),
            f'--remote-debugging-port={port}',
            f'--user-data-dir={profile_dir}',
            '--no-first-run',
            '--new-window',
            'about:blank',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        wait_for_devtools(port)
        page_info = get_devtools_page(port)
        ws_url = page_info.get('webSocketDebuggerUrl')
        if not ws_url:
            raise RuntimeError(f'浏览器页面缺少调试地址：{page_info!r}')

        deadline = time.monotonic() + timeout
        login_requests = set()
        login_responses = set()
        print('浏览器已打开，请在页面里完成 Erolabs 登录...')

        with DevToolsWebSocket(ws_url) as cdp:
            cdp.command('Network.enable')
            cdp.command('Page.enable')
            cdp.command('Page.navigate', {'url': LOGIN_PAGE})

            while time.monotonic() < deadline:
                try:
                    event = cdp.recv_json()
                except socket.timeout:
                    continue

                if 'id' in event:
                    continue

                method = event.get('method')
                params = event.get('params', {})
                if method == 'Network.requestWillBeSent':
                    request = params.get('request', {})
                    request_id = params.get('requestId')
                    if (
                        request_id
                        and LOGIN_URL in request.get('url', '')
                        and request.get('method', '').upper() == 'POST'
                    ):
                        login_requests.add(request_id)
                elif method == 'Network.responseReceived':
                    response = params.get('response', {})
                    request_id = params.get('requestId')
                    if request_id in login_requests and LOGIN_URL in response.get('url', ''):
                        print(f'捕获登录响应：HTTP {int(response.get("status", 0))}')
                        login_responses.add(request_id)
                elif method == 'Network.loadingFinished':
                    request_id = params.get('requestId')
                    if request_id not in login_responses:
                        continue
                    cmd_id = cdp.command('Network.getResponseBody', {'requestId': request_id})
                    while time.monotonic() < deadline:
                        try:
                            msg = cdp.recv_json()
                        except socket.timeout:
                            continue
                        if msg.get('id') != cmd_id:
                            continue
                        if 'error' in msg:
                            raise RuntimeError(f'无法读取登录响应：{msg["error"]}')
                        return extract_login_payload(parse_cdp_body(msg.get('result', {})))
    finally:
        if proc.poll() is None:
            proc.terminate()

    raise TimeoutError('等待登录超时')


def print_login_payload(payload):
    print(f'nickname: {payload.get("nickName") or payload.get("nickname")}')
    print(f'jwt: {payload.get("jwt")}')


def main():
    try:
        print_login_payload(capture_login())
    except Exception as exc:
        print(f'登录失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
