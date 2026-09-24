"""
ابزار همگام‌سازی نام کانفیگ با بدنه لینک.
"""
import base64
import json
from urllib.parse import quote


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
