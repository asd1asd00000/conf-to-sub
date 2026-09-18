"""
Health Checker - تست واقعی اتصال با Xray (فقط برای علامت‌گذاری ✅)
هیچ کانفیگ معتبری بر اساس این تست حذف نمی‌شود.
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
TEST_TIMEOUT = 6
TEST_URL = "https://www.google.com/generate_204"
SOCKS_PORT_MIN = 20000
PORT_POOL_SIZE = 64
CONCURRENT = 6

MARK_OK = "✅"  # پیشوند کانفیگ‌های تأییدشده

RESULT_VERIFIED = "verified"  # ذخیره + ✅
RESULT_SAVED = "saved"        # ذخیره بدون علامت
RESULT_DISCARD = "discard"    # فرمت نامعتبر -> دور ریختن


def find_xray():
    path = shutil.which("xray")
    if path:
        return path
    for p in ("/usr/local/bin/xray", "/usr/bin/xray"):
        if os.path.exists(p):
            return p
    return None


def find_curl():
    path = shutil.which("curl")
    if path:
        return path
    for p in ("/usr/bin/curl", "/bin/curl"):
        if os.path.exists(p):
            return p
    return None


SUPPORTED_PREFIXES = ("vmess://", "vless://", "trojan://", "ss://", "ssr://",
                      "hysteria://", "hysteria2://", "hy2://", "tuic://")


def validate_format(link: str) -> bool:
    """بررسی آفلاین ساختار لینک (بدون شبکه)."""
    link = (link or "").strip()
    if not link or len(link) < 20:
        return False
    if not link.startswith(SUPPORTED_PREFIXES):
        return False
    if link.startswith("vmess://"):
        try:
            raw = base64.standard_b64decode(link[8:]).decode("utf-8")
            o = json.loads(raw)
            return bool(o.get("add") and o.get("id") and o.get("port"))
        except Exception:
            return False
    if link.startswith(("vless://", "trojan://")):
        try:
            p = urlparse(link)
            return bool(p.hostname and p.port and "@" in p.netloc)
        except Exception:
            return False
    if link.startswith("ss://"):
        return ("@" in link) or (":" in link[5:])
    return True  # ssr / hysteria2 / tuic: قبول می‌شوند (تست‌ناپذیر)


# ================= پارسرها =================

def _stream_settings(net="tcp", tls=False, sni="", alpn="h2,http/1.1", fp="chrome",
                     path="/", host="", grpc_service="", security="tls",
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
        stream["wsSettings"] = {"path": path or "/", "headers": {"Host": host or sni} if (host or sni) else {}}
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
    address = o.get("add") or ""
    port = int(o.get("port", 443))
    uid = o.get("id") or ""
    if not address or not uid:
        return None
    return {
        "protocol": "vmess", "tag": "proxy",
        "settings": {"vnext": [{"address": address, "port": port,
                                "users": [{"id": uid,
                                           "security": (o.get("scy") or "auto").strip() or "auto",
                                           "alterId": int(o.get("aid", 0))}]}]},
        "streamSettings": _stream_settings(
            net=(o.get("net") or "tcp").strip().lower(),
            tls=(o.get("tls") or "0").strip().lower() in ("1", "true", "tls"),
            sni=(o.get("sni") or o.get("host") or address).strip(),
            alpn=(o.get("alpn") or "h2,http/1.1").strip(),
            fp=(o.get("fp") or "chrome").strip(),
            path=(o.get("path") or "/").strip(),
            host=(o.get("host") or (o.get("sni") or address)).strip()),
    }


def parse_vless(link):
    if not link.startswith("vless://"):
        return None
    try:
        parsed = urlparse(link)
        if "@" not in parsed.netloc:
            return None
        userinfo, host_port = parsed.netloc.rsplit("@", 1)
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
        flow = get("flow", "")
        user = {"id": userinfo, "encryption": "none"}
        if flow:
            user["flow"] = flow
        return {
            "protocol": "vless", "tag": "proxy",
            "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
            "streamSettings": _stream_settings(
                net=get("type", "tcp").lower(), tls=security in ("tls", "reality"),
                sni=sni, alpn=get("alpn", "h2,http/1.1"), fp=get("fp", "chrome"),
                path=get("path", "/"), host=get("host") or sni,
                grpc_service=get("serviceName", ""), security=security,
                reality_pbk=get("pbk") or get("publicKey", ""),
                reality_sid=get("sid") or get("shortId", ""),
                reality_spx=get("spx") or get("spiderX", "")),
        }
    except Exception:
        return None


def parse_trojan(link):
    if not link.startswith("trojan://"):
        return None
    try:
        parsed = urlparse(link)
        if "@" not in parsed.netloc:
            return None
        password, host_port = parsed.netloc.rsplit("@", 1)
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
        return {
            "protocol": "trojan", "tag": "proxy",
            "settings": {"servers": [{"address": host, "port": port, "password": password}]},
            "streamSettings": _stream_settings(
                net=get("type", "tcp").lower(), tls=security in ("tls", "reality"),
                sni=sni, alpn=get("alpn", "h2,http/1.1"), fp=get("fp", "chrome"),
                path=get("path", "/"), host=get("host") or sni,
                grpc_service=get("serviceName", ""), security=security,
                reality_pbk=get("pbk") or get("publicKey", ""),
                reality_sid=get("sid") or get("shortId", ""),
                reality_spx=get("spx") or get("spiderX", "")),
        }
    except Exception:
        return None


def parse_ss(link):
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
                return None
        if "@" in body:
            userinfo, hostport = body.rsplit("@", 1)
            padded = userinfo + "=" * ((4 - len(userinfo) % 4) % 4)
            dec = base64.standard_b64decode(padded).decode("utf-8")
            method, password = dec.split(":", 1)
        else:
            padded = body + "=" * ((4 - len(body) % 4) % 4)
            dec = base64.standard_b64decode(padded).decode("utf-8")
            mp, hostport = dec.rsplit("@", 1)
            method, password = mp.split(":", 1)
        host, port_s = hostport.rsplit(":", 1)
        return {"protocol": "shadowsocks", "tag": "proxy",
                "settings": {"servers": [{"address": host, "port": int(port_s),
                                          "method": method, "password": password}]}}
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
    link = link.strip()
    if "#" in link:
        try:
            return unquote(link.split("#", 1)[1].strip()[:80])
        except Exception:
            pass
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
    return {
        "log": {"loglevel": "error"},
        "inbounds": [{"listen": "127.0.0.1", "port": socks_port,
                      "protocol": "socks", "settings": {"udp": False}}],
        "outbounds": [outbound, {"protocol": "freedom", "tag": "direct"}],
    }


def run_xray_and_test(config_path, socks_port, timeout=TEST_TIMEOUT):
    xray_path = find_xray()
    curl_path = find_curl()
    if not xray_path or not curl_path:
        return False, "xray/curl not found"
    try:
        proc = subprocess.Popen([xray_path, "run", "-config", config_path],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False, "xray not found"
    try:
        time.sleep(1)
        try:
            r = subprocess.run(
                [curl_path, "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "-m", str(max(timeout - 2, 2)),
                 "--socks5-hostname", f"127.0.0.1:{socks_port}", TEST_URL],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
            code = r.stdout.decode("utf-8", errors="ignore").strip()
            return (r.returncode == 0 and code in ("200", "204")), (code or f"curl:{r.returncode}")
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, type(e).__name__
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def check_links_batch(links, timeout=TEST_TIMEOUT, concurrent=CONCURRENT, log=print):
    results = [RESULT_SAVED] * len(links)
    port_pool = Queue()
    for i in range(PORT_POOL_SIZE):
        port_pool.put(SOCKS_PORT_MIN + i)

    def work(item):
        idx, link = item
        try:
            if not validate_format(link):
                log(f"   [DISCARD] فرمت نامعتبر: {link[:50]}")
                return idx, RESULT_DISCARD
            outbound = parse_link(link)
            if outbound is None:
                log(f"   [SAVE] پروتکل تست‌ناپذیر: {link[:50]}")
                return idx, RESULT_SAVED
            port = port_pool.get()
            fd, path = tempfile.mkstemp(suffix=".json")
            try:
                config = build_xray_config(outbound, port)
                os.write(fd, json.dumps(config).encode("utf-8"))
                os.close(fd)
                fd = None
                ok, res = run_xray_and_test(path, port, timeout)
                if ok:
                    log(f"   [VERIFIED ✅] {res} | {link[:50]}")
                    return idx, RESULT_VERIFIED
                log(f"   [SAVE] تست ناموفق ({res}): {link[:50]}")
                return idx, RESULT_SAVED
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
            log(f"   [SAVE] خطا ({e}): {link[:50]}")
            return idx, RESULT_SAVED

    with ThreadPoolExecutor(max_workers=max(1, concurrent)) as ex:
        for idx, status in ex.map(work, enumerate(links)):
            results[idx] = status
    return results


async def check_configs(links, timeout=TEST_TIMEOUT, concurrent=CONCURRENT):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_links_batch, links, timeout, concurrent)
