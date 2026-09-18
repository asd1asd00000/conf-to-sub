import asyncio
import json
import os
import subprocess
import tempfile
import base64
import shutil
import random
from urllib.parse import urlparse, parse_qs, unquote

XRAY_PATH = "/usr/local/bin/xray"
CURL_PATH = "/usr/bin/curl"

async def test_config_health(config_link: str, timeout: int = 12) -> bool:
    """
    تابع اصلی برای تست سلامت کانفیگ به صورت Async
    timeout: حداکثر زمان انتظار (ثانیه)
    """
    if not config_link.startswith(("vless://", "vmess://", "trojan://", "tuic://", "hysteria2://", "ss://", "ssr://")):
        print(f"⚠️ پروتکل پشتیبانی نشده: {config_link[:30]}...")
        return False

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _run_xray_test, config_link, timeout)
    except Exception as e:
        print(f"❌ خطای Async در تست: {e}")
        return False

def _get_random_port() -> int:
    """تولید یک پورت تصادفی بین 10000 و 60000"""
    return random.randint(10000, 60000)

def _run_xray_test(config_link: str, timeout: int) -> bool:
    """
    اجرای Xray با پورت تصادفی و تست اتصال
    """
    # تولید پورت منحصر به فرد برای هر تست
    socks_port = _get_random_port()
    
    temp_dir = tempfile.mkdtemp()
    config_path = os.path.join(temp_dir, "config.json")
    
    try:
        # ۱. تبدیل لینک به JSON با پورت تصادفی
        xray_config = _generate_xray_config(config_link, socks_port)
        if not xray_config:
            print(f"❌ خطا در تولید JSON. لینک: {config_link[:40]}...")
            return False
            
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(xray_config, f, ensure_ascii=False)
        
        # ۲. اجرای Xray
        process = subprocess.Popen(
            [XRAY_PATH, "run", "-config", config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # ۳. صبر برای بالا آمدن Xray (افزایش به ۲.۵ ثانیه)
        import time
        time.sleep(2.5)
        
        # ۴. بررسی اینکه آیا پروسه Xray هنوز زنده است یا خیر
        if process.poll() is not None:
            # پروسه مرده است، لاگ خطا را بگیر
            _, stderr = process.communicate()
            print(f"❌ Xray کرش کرد: {stderr.decode('utf-8', errors='ignore').strip()}")
            return False
        
        # ۵. تست اتصال با curl از طریق پورت SOCKS منحصر به فرد
        is_healthy = False
        
        # لیست URL‌های مختلف برای تست (اگر یکی کار نکرد، بعدی را امتحان کن)
        test_urls = [
            "http://www.gstatic.com/generate_204",
            "http://cp.cloudflare.com/generate_204",
            "http://connectivitycheck.gstatic.com/generate_204"
        ]
        
        for test_url in test_urls:
            try:
                result = subprocess.run(
                    [CURL_PATH, "-s", "-o", "/dev/null", "-w", "%{http_code}", 
                     "-m", str(timeout - 3),  # ۳ ثانیه کمتر از timeout کل
                     "--socks5-hostname", f"127.0.0.1:{socks_port}", 
                     test_url],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout - 2
                )
                
                http_code = result.stdout.decode('utf-8').strip()
                
                # HTTP 204 یا 200 یعنی موفق
                if result.returncode == 0 and http_code in ["204", "200"]:
                    is_healthy = True
                    print(f"✅ اتصال موفق (HTTP {http_code}) از طریق {test_url}")
                    break
                else:
                    print(f"⚠️ تست با {test_url} ناموفق بود (کد: {http_code})")
                    
            except subprocess.TimeoutExpired:
                print(f"⚠️ Timeout برای {test_url}")
                continue
            except Exception as e:
                print(f"⚠️ خطا در curl برای {test_url}: {e}")
                continue
        
        # ۶. بستن پروسه Xray
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            
        return is_healthy
        
    except Exception as e:
        print(f"❌ خطای اجرای Xray: {e}")
        return False
    finally:
        # پاک‌سازی فایل‌های موقت
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

def _generate_xray_config(link: str, socks_port: int) -> dict:
    """
    تشخیص پروتکل و فراخوانی پارسر مناسب با پورت SOCKS دلخواه
    """
    try:
        if link.startswith("vmess://"):
            outbound = _parse_vmess(link)
        elif link.startswith("ss://"):
            outbound = _parse_shadowsocks(link)
        elif link.startswith("ssr://"):
            outbound = _parse_ssr(link)
        else:
            protocol = link.split("://")[0]
            outbound = _parse_uri(link, protocol)
            
        if not outbound:
            return None
            
        return {
            "log": {"loglevel": "error"},
            "inbounds": [{
                "port": socks_port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
                "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
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
    """پارسر VMess"""
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
                    "users": [{
                        "id": data['id'],
                        "alterId": int(data.get('aid', 0)),
                        "security": data.get('scy', 'auto'),
                        "level": 8
                    }]
                }]
            },
            "streamSettings": {"network": stream, "security": security}
        }

        if security == 'tls':
            tls_settings = {
                "serverName": data.get('sni', data.get('host', data['add'])),
                "fingerprint": data.get('fp', 'chrome'),
                "allowInsecure": True
            }
            if data.get('alpn'):
                tls_settings["alpn"] = data['alpn'].split(',')
            outbound["streamSettings"]["tlsSettings"] = tls_settings
            
        _apply_transport_vmess(outbound, stream, data)
        return outbound
    except Exception as e:
        print(f"❌ خطای پارس VMess: {e}")
        return None

def _parse_shadowsocks(link: str) -> dict:
    """پارسر Shadowsocks"""
    try:
        parts = link.split("://")
        if len(parts) != 2:
            return None
            
        # فرمت: ss://base64(method:password)@host:port#name
        # یا: ss://base64(method:password@host:port)#name
        
        content = parts[1]
        if "#" in content:
            content = content.split("#")[0]
            
        if "@" in content:
            userinfo, hostport = content.split("@", 1)
            method_pass = base64.b64decode(userinfo + "=" * ((4 - len(userinfo) % 4) % 4)).decode('utf-8')
            method, password = method_pass.split(":", 1)
            host, port = hostport.split(":", 1)
        else:
            # فرمت قدیمی
            decoded = base64.b64decode(content + "=" * ((4 - len(content) % 4) % 4)).decode('utf-8')
            method_pass, hostport = decoded.split("@", 1)
            method, password = method_pass.split(":", 1)
            host, port = hostport.split(":", 1)
            
        return {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": host,
                    "port": int(port),
                    "method": method,
                    "password": password,
                    "level": 8
                }]
            }
        }
    except Exception as e:
        print(f"❌ خطای پارس Shadowsocks: {e}")
        return None

def _parse_ssr(link: str) -> dict:
    """پارسر SSR (ShadowsocksR) - پشتیبانی محدود"""
    try:
        b64 = link.split("://")[1]
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        decoded = base64.b64decode(b64).decode('utf-8')
        
        # فرمت: host:port:protocol:method:obfs:base64(password)/?params
        parts = decoded.split(":")
        if len(parts) < 6:
            return None
            
        host = parts[0]
        port = int(parts[1])
        method = parts[3]
        
        # استخراج password (base64 encoded)
        password_part = parts[5].split("/")[0]
        password = base64.b64decode(password_part + "=" * ((4 - len(password_part) % 4) % 4)).decode('utf-8')
        
        return {
            "protocol": "shadowsocks",  # Xray SSR را به عنوان shadowsocks ساده پشتیبانی می‌کند
            "settings": {
                "servers": [{
                    "address": host,
                    "port": port,
                    "method": method,
                    "password": password,
                    "level": 8
                }]
            }
        }
    except Exception as e:
        print(f"❌ خطای پارس SSR: {e}")
        return None

def _parse_uri(link: str, protocol: str) -> dict:
    """پارسر عمومی برای VLESS, Trojan, Hysteria2, TUIC"""
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
        allow_insecure = get_param('allowInsecure', '0') == '1'

        outbound = {
            "protocol": protocol,
            "settings": {},
            "streamSettings": {"network": type_, "security": security}
        }

        # تنظیمات اختصاصی هر پروتکل
        if protocol == 'vless':
            outbound["settings"]["vnext"] = [{
                "address": host, "port": port,
                "users": [{
                    "id": user_info, 
                    "flow": get_param('flow', ''), 
                    "encryption": "none",
                    "level": 8
                }]
            }]
        elif protocol == 'trojan':
            outbound["settings"]["servers"] = [{
                "address": host, "port": port, 
                "password": user_info,
                "level": 8
            }]
        elif protocol in ['hysteria2', 'tuic']:
            settings = {"servers": [{"address": host, "port": port}]}
            if protocol == 'hysteria2':
                settings["servers"][0]["password"] = user_info
            elif protocol == 'tuic':
                settings["servers"][0]["uuid"] = user_info
                settings["servers"][0]["password"] = get_param('password', '')
            outbound["settings"] = settings

        # تنظیمات Security (TLS / Reality)
        if security == 'tls':
            tls_settings = {
                "serverName": sni, 
                "fingerprint": fp,
                "allowInsecure": allow_insecure
            }
            if alpn:
                tls_settings["alpn"] = alpn.split(",")
            outbound["streamSettings"]["tlsSettings"] = tls_settings
        elif security == 'reality':
            outbound["streamSettings"]["realitySettings"] = {
                "serverName": sni,
                "publicKey": get_param('pbk', ''),
                "shortId": get_param('sid', ''),
                "spiderX": get_param('spx', '/'),
                "fingerprint": fp
            }

        # اعمال تنظیمات ترنسپورت
        _apply_transport(outbound, type_, params)
        return outbound
    except Exception as e:
        print(f"❌ خطای پارس URI ({protocol}): {e}")
        return None

def _apply_transport_vmess(outbound: dict, network: str, data: dict):
    """اعمال ترنسپورت برای VMess"""
    stream = outbound["streamSettings"]
    
    if network == 'ws':
        stream["wsSettings"] = {
            "path": data.get('path', '/'),
            "headers": {"Host": data.get('host', '')}
        }
    elif network == 'grpc':
        stream["grpcSettings"] = {
            "serviceName": data.get('path', '')
        }
    elif network == 'httpupgrade':
        stream["httpupgradeSettings"] = {
            "path": data.get('path', '/'),
            "host": data.get('host', '')
        }
    elif network == 'tcp' and data.get('type') == 'http':
        stream["tcpSettings"] = {
            "header": {
                "type": "http",
                "request": {"path": [data.get('path', '/')]},
                "response": {}
            }
        }

def _apply_transport(outbound: dict, network: str, params: dict):
    """اعمال تنظیمات شبکه (WebSocket, gRPC, HTTPUpgrade)"""
    def get_param(key, default=None):
        val = params.get(key, [default])[0]
        return val if val else default

    stream = outbound["streamSettings"]
    
    if network == 'ws':
        stream["wsSettings"] = {
            "path": get_param('path', '/'),
            "headers": {"Host": get_param('host', '')}
        }
    elif network == 'grpc':
        stream["grpcSettings"] = {
            "serviceName": get_param('serviceName', '')
        }
    elif network == 'httpupgrade':
        stream["httpupgradeSettings"] = {
            "path": get_param('path', '/'),
            "host": get_param('host', '')
        }
    elif network == 'tcp' and get_param('headerType') == 'http':
        stream["tcpSettings"] = {
            "header": {
                "type": "http",
                "request": {"path": [get_param('path', '/')]},
                "response": {}
            }
        }
    elif network == 'splithttp' or network == 'xhttp':
        stream["splithttpSettings"] = {
            "path": get_param('path', '/'),
            "host": get_param('host', '')
        }
