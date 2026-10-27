import json
from pathlib import Path


def load_cookies_for_playwright(path: str):
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cookies = []
    for c in raw:
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".tiktok.com"),
            "path": c.get("path", "/"),
        }
        same_site = c.get("sameSite", "Lax")
        if same_site not in ("Strict", "Lax", "None"):
            same_site = "Lax"
        cookie["sameSite"] = same_site
        if "expirationDate" in c:
            cookie["expires"] = c["expirationDate"]
        if "httpOnly" in c:
            cookie["httpOnly"] = c["httpOnly"]
        if "secure" in c:
            cookie["secure"] = c["secure"]
        cookies.append(cookie)
    return cookies
