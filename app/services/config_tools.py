"""
ابزارهای کانفیگ: همگام‌سازی نام + اثر انگشت تشخیص تکراری.
"""
import base64
import json
from urllib.parse import urlparse, quote


def apply_remark_to_raw(raw: str, remark: str) -> str:
    raw = (raw or "").strip()
    remark = (remark or "").strip()
    if not raw or not remark:
        return raw
    try:
        if raw.startswith("vmess://"):
            payload = raw[len("vmess://"):]
            pad = "=" * (-len(payload) % 4)
            data = json.loads(base64.b64decode(payload + pad).decode("utf-8"))
            data["ps"] = remark
            new_payload = base64.b64encode(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            ).decode()
            return "vmess://" + new_payload
        if "://" in raw:
            base = raw.split("#")[0]
            return base + "#" + quote(remark, safe="")
    except Exception:
        return raw
    return raw


def config_fingerprint(raw: str):
    """
    اثر انگشت = protocol|uuid|address|port
    کانفیگ‌های «شبیه به هم» (تفاوت فقط در sni/host/path/remark) اثر انگشت یکسان می‌گیرند.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        if raw.startswith("vless://") or raw.startswith("trojan://"):
            u = urlparse(raw)
            if not u.hostname or not u.port:
                return None
            proto = "vless" if raw.startswith("vless://") else "trojan"
            return f"{proto}|{u.username or ''}|{u.hostname.lower()}|{u.port}"

        if raw.startswith("vmess://"):
            payload = raw[len("vmess://"):]
            pad = "=" * (-len(payload) % 4)
            d = json.loads(base64.b64decode(payload + pad).decode("utf-8"))
            addr = (d.get("add") or "").lower()
            port = d.get("port")
            uid = d.get("id") or ""
            if not addr or not port:
                return None
            return f"vmess|{uid}|{addr}|{port}"

        if raw.startswith("ss://"):
            body = raw[len("ss://"):].split("#")[0]
            u = urlparse("ss://" + body)
            if u.hostname and u.port:
                return f"ss|{u.username or ''}|{u.hostname.lower()}|{u.port}"
            pad = "=" * (-len(body) % 4)
            dec = base64.b64decode(body + pad).decode("utf-8")
            if "@" in dec:
                left, right = dec.rsplit("@", 1)
                addr, port = right.rsplit(":", 1)
                return f"ss|{left}|{addr.lower()}|{port}"
            return None

        if raw.startswith("ssr://"):
            body = raw[len("ssr://"):].split("#")[0]
            pad = "=" * (-len(body) % 4)
            dec = base64.b64decode(body + pad).decode("utf-8")
            parts = dec.split("/?")[0].split(":")
            if len(parts) >= 6:
                p2 = parts[5]
                pad2 = "=" * (-len(p2) % 4)
                pwd = base64.b64decode(p2 + pad2).decode("utf-8")
                return f"ssr|{pwd}|{parts[0].lower()}|{parts[1]}"
            return None
    except Exception:
        return None
    return None
