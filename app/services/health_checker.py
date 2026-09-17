import asyncio
import json
import os
import subprocess
import tempfile
import base64
import shutil
from urllib.parse import urlparse, parse_qs, unquote

XRAY_PATH = "/usr/local/bin/xray"
CURL_PATH = "/usr/bin/curl"  # <-- مسیر دقیق curl اضافه شد
SOCKS_PORT = 1080

async def test_config_health(config_link: str, timeout: int = 5) -> bool:
    if not config_link.startswith(("vless://", "vmess://", "trojan://", "tuic://", "hysteria2://")):
        print(f"⚠️ پروتکل پشتیبانی نشده یا فرمت اشتباه: {config_link[:20]}...")
        return False

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _run_xray_test, config_link, timeout)
    except Exception as e:
        print(f"❌ خطای Async در تست: {e}")
        return False

def _run_xray_test(config_link: str, timeout: int) -> bool:
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, "config.json")
    
    try:
        xray_config = _generate_xray_config(config_link)
        if not xray_config:
            print(f"❌ خطا در تولید JSON برای Xray. لینک: {config_link[:30]}...")
            return False
            
        with open(config_path, "w") as f:
            json.dump(xray_config, f)
        
        process = subprocess.Popen(
            [XRAY_PATH, "run", "-config", config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        import time
        time.sleep(1.5)
        
        is_healthy = False
        try:
            # استفاده از مسیر دقیق curl
            result = subprocess.run(
                [CURL_PATH, "-s", "-m", "4", "--socks5-hostname", f"127.0.0.1:{SOCKS_PORT}", "http://www.gstatic.com/generate_204"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            
            if result.returncode == 0:
                is_healthy = True
            else:
                print(f"❌ خطای Curl (کد {result.returncode}). خروجی: {result.stderr.decode('utf-8', errors='ignore').strip()}")
                
        except Exception as e:
            print(f"❌ خطای اتصال Curl: {e}")
            is_healthy = False
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
            
        return is_healthy
        
    except Exception as e:
        print(f"❌ خطای اجرای Xray: {e}")
        return False
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def _generate_xray_config(link: str) -> dict:
    try:
        if link.startswith("vmess://"):
            outbound = _parse_vmess(link)
        else:
            protocol = link.split("://")[0]
            outbound = _parse_uri(link, protocol)
            
        if not outbound:
            return None
            
        return {
            "log": {"loglevel": "warning"},
            "inbounds": [{
                "port": SOCKS_PORT,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True}
            }],
            "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [{"type": "field", "outboundTag": "direct", "domain": ["geosite:private"]}]
            }
        }
    except Exception as e:
        print(f"❌ خطای تولید کانفیگ: {e}")
        return None

def _parse_vmess(link: str) -> dict:
    try:
        b64 = link.split("://")[1]
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        data = json.loads(base64.b64decode(b64).decode('utf-8'))

        stream = data.get('net', 'tcp')
        security = 'tls' if data.get('tls') == 'tls' else 'none'

        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": data['add'],
                    "port": int(data['port']),
                    "users": [{"id": data['id'], "alterId": int(data.get('aid', 0)), "security": data.get('scy', 'auto')}]
                }]
            },
            "streamSettings": {"network": stream, "security": security}
        }

        if security == 'tls':
            outbound["streamSettings"]["tlsSettings"] = {"serverName": data.get('sni', data['add']), "fingerprint": data.get('fp', 'chrome')}
            
        _apply_transport(outbound, stream, data)
        return outbound
    except Exception as e:
        print(f"❌ خطای پارس VMess: {e}")
        return None

def _parse_uri(link: str, protocol: str) -> dict:
    try:
        parsed = urlparse(link)
        host = parsed.hostname
        port = parsed.port
        user_info = unquote(parsed.username) if parsed.username else ""
        if protocol == 'trojan':
            user_info = unquote(parsed.password) if parsed.password else ""

        params = parse_qs(parsed.query)
        def get_param(key, default=None):
            val = params.get(key, [default])[0]
            return val if val else default

        security = get_param('security', 'none')
        sni = get_param('sni', host)
        fp = get_param('fp', 'chrome')
        type_ = get_param('type', 'tcp')
        alpn = get_param('alpn', '')

        outbound = {
            "protocol": protocol,
            "settings": {},
            "streamSettings": {"network": type_, "security": security}
        }

        if protocol == 'vless':
            outbound["settings"]["vnext"] = [{"address": host, "port": port, "users": [{"id": user_info, "flow": get_param('flow', ''), "encryption": "none"}]}]
        elif protocol == 'trojan':
            outbound["settings"]["servers"] = [{"address": host, "port": port, "password": user_info}]
        elif protocol in ['hysteria2', 'tuic']:
            outbound["settings"]["servers"] = [{"address": host, "port": port, "password": user_info if protocol == 'hysteria2' else None, "users": [{"password": user_info}] if protocol == 'tuic' else None}]

        if security == 'tls':
            tls_settings = {"serverName": sni, "fingerprint": fp}
            if alpn: tls_settings["alpn"] = alpn.split(",")
            outbound["streamSettings"]["tlsSettings"] = tls_settings
        elif security == 'reality':
            outbound["streamSettings"]["realitySettings"] = {"serverName": sni, "publicKey": get_param('pbk', ''), "shortId": get_param('sid', ''), "spiderX": get_param('spx', '/'), "fingerprint": fp}

        _apply_transport(outbound, type_, params)
        return outbound
    except Exception as e:
        print(f"❌ خطای پارس URI ({protocol}): {e}")
        return None

def _apply_transport(outbound: dict, network: str, params: dict):
    def get_param(key, default=None):
        val = params.get(key, [default])[0]
        return val if val else default

    stream = outbound["streamSettings"]
    if network == 'ws':
        stream["wsSettings"] = {"path": get_param('path', '/'), "headers": {"Host": get_param('host', '')}}
    elif network == 'grpc':
        stream["grpcSettings"] = {"serviceName": get_param('serviceName', '')}
    elif network == 'httpupgrade':
        stream["httpupgradeSettings"] = {"path": get_param('path', '/'), "host": get_param('host', '')}
    elif network == 'tcp' and get_param('headerType') == 'http':
        stream["tcpSettings"] = {"header": {"type": "http", "request": {"path": [get_param('path', '/')]}, "response": {}}}
