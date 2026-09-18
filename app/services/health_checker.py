"""
Health Checker - Adapted from the proven v2ray_checker logic.
Runs a real Xray instance per config and verifies connectivity via SOCKS + HTTP check.
"""
import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from urllib.parse import parse_qs, unquote, urlparse

# ------------------ تنظیمات ------------------
TEST_TIMEOUT = 8        # ثانیه برای هر کانفیگ
TEST_URL = "https://www.google.com/generate_204"
SOCKS_PORT_MIN = 20000
PORT_POOL_SIZE = 64
CONCURRENT = 4          # تعداد تست همزمان

STATUS_OK = "ok"
STATUS_FAIL = "fail"
STATUS_UNTESTABLE = "untestable"


def find_xray():
    path = shutil.which("xray")
    if path:
        return path
    for p in ("/usr/local/bin/xray", "/usr/bin/xray", "/usr/local/sbin/xray"):
        if os.path.exists(p):
            return p
    return None


def find_curl():
    path = shutil.which("curl")
    if path:
        return path
    for p in ("/usr/bin/curl", "/bin/curl", "/usr/local/bin/curl"):
        if os.path.exists(p):
            return p
    return None


# ================= پارسرها =================

def _stream_settings(net="tcp", tls=False, sni="", alpn="h2,http/1.1", fp="chrome",
                     path="/", host="", typ="none", grpc_service="", security="tls",
                     reality_pbk="", reality_sid="", reality_spx=""):
    ns = net if net in ("tcp", "ws", "grpc", "http", "h2") else "tcp"
    sec = "tls" if tls else "none"
    if security == "reality":
        sec = "reality"

    stream = {"network": ns, "security": sec}

    if sec == "tls":
        stream["tlsSettings"] = {
            "serverName": sni or host,
            "fingerprint": fp or "chrome",
            "alpn": [s.strip() for s in (alpn or "h2,http/1.1").split(",") if s.strip()],
        }
    elif sec == "reality":
        stream["realitySettings"] = {
            "serverName": sni or host,
            "fingerprint": fp or "chrome",
            "publicKey": reality_pbk,
            "shortId": reality_sid or "",
            **({"spiderX": reality_spx} if reality_spx else {}),
        }

    if ns == "ws":
        stream["wsSettings"] = {
            "path": path or "/",
            "headers": {"Host": host or sni} if (host or sni) else {},
        }
    elif ns == "grpc":
        stream["grpcSettings"] = {"serviceName": grpc_service or ""}
    elif ns in ("http", "h2"):
        stream["httpSettings"] = {"path": path or "/", "host": [host or sni] if (host or sni) else []}

    return stream


def parse_vmess(link):
    if not link.startswith("vmess://"):
        return None
    try:
        raw = base64.standard_b64decode(link[8:]).decode("utf-8")
        o = json.loads(raw)
    except Exception:
        return None
    address = o.get("add") or o.get("address") or ""
    port = int(o.get("port", 443))
    uid = o.get("id") or o.get("uuid") or ""
    if not address or not uid:
        return None
    security = (o.get("scy") or o.get("security") or "auto").strip() or "auto"
    net = (o.get("net") or o.get("network") or "tcp").strip().lower()
    tls = (o.get("tls") or "0").strip().lower() in ("1", "true", "tls", "yes")
    sni = (o.get("sni") or o.get("host") or address).strip()
    alpn = (o.get("alpn") or "h2,http/1.1").strip()
    fp = (o.get("fp") or "chrome").strip()
    path = (o.get("path") or "/").strip()
    host = (o.get("host") or sni).strip()
    typ = (o.get("type") or "none").strip()

    return {
        "protocol": "vmess",
        "tag": "proxy",
        "settings": {
            "vnext": [{
                "address": address,
                "port": port,
                "users": [{"id": uid, "security": security, "alterId": int(o.get("aid", 0))}],
            }]
        },
        "streamSettings": _stream_settings(net=net, tls=tls, sni=sni, alpn=alpn, fp=fp,
                                           path=path, host=host, typ=typ),
    }


def parse_vless(link):
    if not link.startswith("vless://"):
        return None
    try:
        parsed = urlparse(link)
        netloc = parsed.netloc
        if "@" not in netloc:
            return None
        userinfo, host_port = netloc.rsplit("@", 1)
        uuid = userinfo
        if ":" in host_port:
            host, port_s = host_port.rsplit(":", 1)
            port = int(port_s)
        else:
            host, port = host_port, 443
        q = parse_qs(parsed.query)

        def get(name, default=""):
            return (q.get(name) or [default])[0].strip()

        security = get("security", "none")
        sni = get("sni") or get("host") or host
        alpn = get("alpn", "h2,http/1.1")
        fp = get("fp", "chrome")
        flow = get("flow", "")
        net = get("type", "tcp").lower()
        path = get("path", "/")
        host_h = get("host") or sni
        service_name = get("serviceName", "")
        pbk = get("pbk") or get("publicKey", "")
        sid = get("sid") or get("shortId", "")
        spx = get("spx") or get("spiderX", "")
    except Exception:
        return None

    user = {"id": uuid, "encryption": "none"}
    if flow:
        user["flow"] = flow

    return {
        "protocol": "vless",
        "tag": "proxy",
        "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
        "streamSettings": _stream_settings(net=net, tls=security in ("tls", "reality"),
                                           sni=sni, alpn=alpn, fp=fp, path=path, host=host_h,
                                           grpc_service=service_name, security=security,
                                           reality_pbk=pbk, reality_sid=sid, reality_spx=spx),
    }


def parse_trojan(link):
    if not link.startswith("trojan://"):
        return None
    try:
        parsed = urlparse(link)
        netloc = parsed.netloc
        if "@" not in netloc:
            return None
        password, host_port = netloc.rsplit("@", 1)
        password = password.strip()
        if ":" in host_port:
            host, port_s = host_port.rsplit(":", 1)
            port = int(port_s)
        else:
            host, port = host_port, 443
        q = parse_qs(parsed.query)

        def get(name, default=""):
            return (q.get(name) or [default])[0].strip()

        security = get("security", "tls")
        sni = get("sni") or get("host") or host
        alpn = get("alpn", "h2,http/1.1")
        fp = get("fp", "chrome")
        flow = get("flow", "")
        net = get("type", "tcp").lower()
        path = get("path", "/")
        host_h = get("host") or sni
        service_name = get("serviceName", "")
        pbk = get("pbk") or get("publicKey", "")
        sid = get("sid") or get("shortId", "")
        spx = get("spx") or get("spiderX", "")
    except Exception:
        return None

    server = {"address": host, "port": port, "password": password}
    if flow:
        server["flow"] = flow

    return {
        "protocol": "trojan",
        "tag": "proxy",
        "settings": {"servers": [server]},
        "streamSettings": _stream_settings(net=net, tls=security in ("tls", "reality"),
                                           sni=sni, alpn=alpn, fp=fp, path=path, host=host_h,
                                           grpc_service=service_name, security=security,
                                           reality_pbk=pbk, reality_sid=sid, reality_spx=spx),
    }


def parse_ss(link):
    """پارسر Shadowsocks (فرمت SIP002 و Legacy). اگر plugin داشته باشد، قابل تست نیست."""
    if not link.startswith("ss://"):
        return None
    try:
        body = link[5:]
        if "#" in body:
            body = body.split("#", 1)[0]
        if "?" in body:
            query = body.split("?", 1)[1]
            body = body.split("?", 1)[0]
            if "plugin=" in query:
                return None  # plugin توسط Xray پشتیبانی نمی‌شود
        else:
            query = ""

        if "@" in body:
            userinfo, hostport = body.rsplit("@", 1)
            padded = userinfo + "=" * ((4 - len(userinfo) % 4) % 4)
            dec = base64.standard_b64decode(padded).decode("utf-8")
            method, password = dec.split(":", 1)
            host, port_s = hostport.rsplit(":", 1)
            port = int(port_s)
        else:
            padded = body + "=" * ((4 - len(body) % 4) % 4)
            dec = base64.standard_b64decode(padded).decode("utf-8")
            mp, hostport = dec.rsplit("@", 1)
            method, password = mp.split(":", 1)
            host, port_s = hostport.rsplit(":", 1)
            port = int(port_s)

        return {
            "protocol": "shadowsocks",
            "tag": "proxy",
            "settings": {"servers": [{
                "address": host, "port": port, "method": method, "password": password,
            }]},
        }
    except Exception:
        return None


def parse_link(link):
    link = link.strip()
    if link.startswith("vmess://"):
        return parse_vmess(link)
    if link.startswith("vless://"):
        return parse_vless(link)
    if link.startswith("trojan://"):
        return parse_trojan(link)
    if link.startswith("ss://"):
        return parse_ss(link)
    return None


def get_remark(link):
    """استخراج نام اصلی کانفیگ (برای تمیزسازی بعدی)."""
    link = link.strip()
    if "#" in link:
        return unquote(link.split("#", 1)[1].strip()[:80])
    if link.startswith("vmess://"):
        try:
            raw = base64.standard_b64decode(link[8:]).decode("utf-8")
            o = json.loads(raw)
            return (o.get("ps") or o.get("name") or "")[:80]
        except Exception:
            pass
    return ""


# ================= اجرای تست =================

def build_xray_config(outbound, socks_port):
    """کانفیگ مینیمال: SOCKS inbound لوکال + proxy outbound + direct. بدون routing و بدون geosite!"""
    return {
        "log": {"loglevel": "error"},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": socks_port,
            "protocol": "socks",
            "settings": {"udp": False},
        }],
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
    }


def run_xray_and_test(config_path, socks_port, timeout=TEST_TIMEOUT):
    """اجرای Xray و تست HTTP از طریق SOCKS با curl. برمی‌گرداند (ok, result_str, ping_ms)."""
    xray_path = find_xray()
    if not xray_path:
        return False, "xray not found", -1.0
    curl_path = find_curl()
    if not curl_path:
        return False, "curl not found", -1.0

    try:
        proc = subprocess.Popen(
            [xray_path, "run", "-config", config_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return False, "xray not found", -1.0

    try:
        time.sleep(1)  # صبر برای بالا آمدن Xray
        t0 = time.perf_counter()
        try:
            r = subprocess.run(
                [curl_path, "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "-m", str(max(timeout - 2, 2)),
                 "--socks5-hostname", f"127.0.0.1:{socks_port}",
                 TEST_URL],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
            ping_ms = (time.perf_counter() - t0) * 1000
            code = r.stdout.decode("utf-8", errors="ignore").strip()
            ok = (r.returncode == 0 and code in ("200", "204"))
            return ok, (code or f"curl:{r.returncode}"), (ping_ms if ok else -1.0)
        except subprocess.TimeoutExpired:
            return False, "timeout", -1.0
        except Exception as e:
            return False, type(e).__name__, -1.0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_links_batch(links, timeout=TEST_TIMEOUT, concurrent=CONCURRENT, log=print):
    """تست دسته‌ای و موازی با استخر پورت. برمی‌گرداند لیست وضعیت هم‌ترتیب با ورودی."""
    results = [STATUS_FAIL] * len(links)
    port_pool = Queue()
    for i in range(PORT_POOL_SIZE):
        port_pool.put(SOCKS_PORT_MIN + i)

    def work(item):
        idx, link = item
        try:
            outbound = parse_link(link)
            if outbound is None:
                # پروتکل‌هایی مثل hysteria2/tuic که Xray پشتیبانی نمی‌کند
                return idx, STATUS_UNTESTABLE, "unsupported protocol (saved without test)"
            port = port_pool.get()
            fd, path = tempfile.mkstemp(suffix=".json")
            try:
                config = build_xray_config(outbound, port)
                os.write(fd, json.dumps(config).encode("utf-8"))
                os.close(fd)
                fd = None
                ok, res, ping_ms = run_xray_and_test(path, port, timeout)
                status = STATUS_OK if ok else STATUS_FAIL
                ping_val = int(ping_ms) if ping_ms >= 0 else -1
                log(f"   [{'OK' if ok else 'FAIL'}] result: {res} | ping: {ping_val} ms | {link[:50]}")
                return idx, status, res
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                try:
                    os.unlink(path)
                except OSError:
                    pass
                port_pool.put(port)
        except Exception as e:
            return idx, STATUS_FAIL, str(e)

    with ThreadPoolExecutor(max_workers=max(1, concurrent)) as ex:
        for idx, status, _res in ex.map(work, enumerate(links)):
            results[idx] = status
    return results


async def check_configs(links, timeout=TEST_TIMEOUT, concurrent=CONCURRENT):
    """نسخه Async برای استفاده در FastAPI."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_links_batch, links, timeout, concurrent)
