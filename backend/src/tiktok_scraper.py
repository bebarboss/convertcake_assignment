import json
import logging
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from cache import get_cached, set_cached
from cookies_utils import load_cookies_for_playwright

logger = logging.getLogger(__name__)

USE_COOKIES = True

DEBUG_DIR = Path("debug_captures")

# เวลาที่รอให้คนแก้ captcha เองในหน้าต่าง Chrome (ตั้งเป็น 0 เพื่อไม่รอ เช่นตอนรันใน Docker)
CAPTCHA_WAIT_SECONDS = int(os.getenv("CAPTCHA_WAIT_SECONDS", "90"))

COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.json")
TOP_N = int(os.getenv("TOP_N", "10"))

REAL_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['th-TH', 'th', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = { runtime: {} };
"""


def _parse_item(item):
    video = item.get("video", {})
    author = item.get("author", {})
    music = item.get("music", {})
    stats = item.get("stats", {})
    hashtags = [
        tag.get("hashtagName")
        for tag in item.get("textExtra", [])
        if tag.get("hashtagName")
    ]

    video_id = item.get("id")
    unique_id = author.get("uniqueId")
    tiktok_url = (
        f"https://www.tiktok.com/@{unique_id}/video/{video_id}"
        if video_id and unique_id else None
    )

    return {
        "id": video_id,
        "tiktok_url": tiktok_url,
        "desc": item.get("desc"),
        "createTime": item.get("createTime"),
        "video_url": video.get("playAddr"),
        "cover": video.get("cover"),
        "author_name": author.get("nickname"),
        "author_id": author.get("id"),
        "author_uniqueId": unique_id,
        "author_avatar": author.get("avatarThumb"),
        "author_region": author.get("region"),
        "music_title": music.get("title"),
        "music_author": music.get("authorName"),
        "hashtags": hashtags,
        "stats": {
            "likes": stats.get("diggCount"),
            "comments": stats.get("commentCount"),
            "shares": stats.get("shareCount"),
            "plays": stats.get("playCount"),
            "favorites": stats.get("collectCount"),
        },
    }


def extract_useful_data(api_response):
    return [_parse_item(entry.get("item", {})) for entry in api_response.get("data", [])]


def get_top_by_likes(data, top_n: int = 10):
    sorted_data = sorted(
        data,
        key=lambda d: (d.get("stats") or {}).get("likes") or 0,
        reverse=True,
    )
    return sorted_data[:top_n]


def parse_count_to_number(text: str):
    if not text:
        return 0
    text = text.strip().upper().replace(",", "")
    multiplier = 1
    if text.endswith("K"):
        multiplier = 1_000
        text = text[:-1]
    elif text.endswith("M"):
        multiplier = 1_000_000
        text = text[:-1]
    elif text.endswith("B"):
        multiplier = 1_000_000_000
        text = text[:-1]
    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0


def _new_stealth_context(browser, **kwargs):
    context = browser.new_context(
        user_agent=REAL_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="th-TH",
        timezone_id="Asia/Bangkok",
        geolocation={"latitude": 13.7563, "longitude": 100.5018},
        permissions=["geolocation"],
        extra_http_headers={
            "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
        },
        **kwargs,
    )
    context.add_init_script(STEALTH_INIT_SCRIPT)

    if USE_COOKIES and Path(COOKIES_FILE).exists():
        cookies = load_cookies_for_playwright(COOKIES_FILE)
        context.add_cookies(cookies)
        logger.info("โหลด cookies แล้ว (USE_COOKIES=true)")
    elif not USE_COOKIES:
        logger.info("ข้ามการโหลด cookies (USE_COOKIES=false) — ทดสอบแบบ guest mode")
    else:
        logger.warning("ไม่พบไฟล์ cookies (%s) — TikTok มีโอกาสบล็อกสูงขึ้นมาก", COOKIES_FILE)

    return context


def _save_debug_capture(page, keyword: str, reason: str):
    try:
        DEBUG_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keyword = "".join(c if c.isalnum() else "_" for c in keyword)[:30]
        base_name = f"{timestamp}_{safe_keyword}_{reason}"

        screenshot_path = DEBUG_DIR / f"{base_name}.png"
        html_path = DEBUG_DIR / f"{base_name}.html"

        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")

        logger.warning(
            "บันทึก debug capture ไว้ที่ %s (.png/.html) — keyword=%r reason=%s",
            base_name, keyword, reason,
        )
    except Exception as e:
        logger.error("บันทึก debug capture ไม่สำเร็จ: %s", e)


def _detect_block_reason(page) -> str | None:
    try:
        checks = {
            "captcha": ["[id*='captcha']", "iframe[src*='captcha']", "text=Verify to continue"],
            "login_wall": ["text=Log in to TikTok", "[data-e2e='login-button']"],
            "rate_limited": ["text=Something went wrong"],
        }
        for reason, selectors in checks.items():
            for sel in selectors:
                if page.query_selector(sel):
                    return reason
    except Exception:
        pass
    return None


def _search_url(keyword: str) -> str:
    return f"https://www.tiktok.com/search?q={quote(keyword)}"


def _profile_url(unique_id: str) -> str:
    return f"https://www.tiktok.com/@{unique_id}"


def get_profile_stats(page, unique_id: str):
    result = {"followers": None, "total_likes": None}
    try:
        page.goto(_profile_url(unique_id), timeout=30000, wait_until="domcontentloaded")
        page.wait_for_selector('[data-e2e="followers-count"]', timeout=10000)

        followers_el = page.query_selector('[data-e2e="followers-count"]')
        if followers_el:
            result["followers"] = parse_count_to_number(followers_el.inner_text())

        likes_el = page.query_selector('[data-e2e="likes-count"]')
        if likes_el:
            result["total_likes"] = parse_count_to_number(likes_el.inner_text())
    except Exception:
        pass

    return result


def dedupe_authors_by_likes(data):
    by_author = {}
    for d in data:
        key = d.get("author_uniqueId") or d.get("author_id")
        if not key:
            continue
        likes = (d.get("stats") or {}).get("likes") or 0

        if key not in by_author:
            by_author[key] = {
                "author_name": d.get("author_name"),
                "author_id": d.get("author_id"),
                "author_uniqueId": d.get("author_uniqueId"),
                "author_avatar": d.get("author_avatar"),
                "top_likes": likes,
                "followers": None,
                "total_likes": None,
            }
        else:
            by_author[key]["top_likes"] = max(by_author[key]["top_likes"], likes)

    return sorted(by_author.values(), key=lambda x: x["top_likes"], reverse=True)


def _block_heavy_resources(route):
    if route.request.resource_type in ("image", "media", "font"):
        route.abort()
    else:
        route.continue_()


def _launch_browser(playwright):
    return playwright.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-sandbox",
        ],
    )


def _search_and_extract(browser, keyword: str):
    search_url = _search_url(keyword)
    api_response = None

    context = _new_stealth_context(browser)
    page = context.new_page()
    page.route("**/*", _block_heavy_resources)

    def handle_response(response):
        nonlocal api_response
        if "api/search/general/full/" in response.url:
            try:
                api_response = response.json()
            except Exception:
                pass

    page.on("response", handle_response)

    page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
    page.wait_for_timeout(10000)

    page.reload(wait_until="domcontentloaded", timeout=10000)
    page.wait_for_timeout(10000)


    if api_response is None:
        reason = _detect_block_reason(page) or "unknown"
        _save_debug_capture(page, keyword, reason)

    useful_data = extract_useful_data(api_response) if api_response else None
    return useful_data, page, context


def scrape_tiktok(
    keywords,
    top_n: int = TOP_N,
    include_author_stats: bool = True,
    candidate_pool: int = 20,
):
    if isinstance(keywords, str):
        keywords = [keywords]

    with sync_playwright() as playwright:
        # เปิด browser เฉพาะตอนที่มีลิงก์ที่ไม่อยู่ใน cache เท่านั้น
        browser = None

        def get_browser():
            nonlocal browser
            if browser is None:
                browser = _launch_browser(playwright)
            return browser

        all_useful_data = []
        seen_video_ids = set()

        for keyword in keywords:
            search_url = _search_url(keyword)
            useful_data = get_cached("search", search_url)
            if useful_data is None:
                useful_data, page, context = _search_and_extract(get_browser(), keyword)
                context.close()
                if useful_data:
                    set_cached(
                        "search", search_url, useful_data,
                        keyword=keyword, videos_count=len(useful_data),
                    )

            if not useful_data:
                continue

            for item in useful_data:
                vid = item.get("id")
                if vid and vid in seen_video_ids:
                    continue
                if vid:
                    seen_video_ids.add(vid)
                all_useful_data.append(item)

        if not all_useful_data:
            if browser:
                browser.close()
            return None

        stats_page = None
        stats_cache = {}

        def get_cached_stats(uid: str):
            nonlocal stats_page
            if uid not in stats_cache:
                profile_url = _profile_url(uid)
                stats = get_cached("profile", profile_url)
                if stats is None:
                    if stats_page is None:
                        stats_page = _new_stealth_context(get_browser()).new_page()
                    stats = get_profile_stats(stats_page, uid)
                    if stats["followers"] is not None:
                        set_cached("profile", profile_url, stats, unique_id=uid, **stats)
                stats_cache[uid] = stats
            return stats_cache[uid]

        videos = get_top_by_likes(all_useful_data, top_n=top_n)
        if include_author_stats:
            for item in videos:
                uid = item.get("author_uniqueId")
                if not uid:
                    item["author_followers"] = None
                    item["author_total_likes"] = None
                    continue
                stats = get_cached_stats(uid)
                item["author_followers"] = stats["followers"]
                item["author_total_likes"] = stats["total_likes"]

        candidates = dedupe_authors_by_likes(all_useful_data)[:candidate_pool]
        for person in candidates:
            uid = person.get("author_uniqueId")
            if uid:
                stats = get_cached_stats(uid)
                person["followers"] = stats["followers"]
                person["total_likes"] = stats["total_likes"]

        if browser:
            browser.close()

    top_authors_list = [p for p in candidates if p["followers"] is not None]
    top_authors_list.sort(key=lambda x: (x["followers"], x["top_likes"]), reverse=True)
    top_authors_list = top_authors_list[:top_n]

    return {"videos": videos, "top_authors": top_authors_list}

def _extract_user_info(page):
    """อ่านข้อมูลโปรไฟล์จาก JSON ที่ TikTok ฝังมากับหน้า (เชื่อถือได้กว่าอ่านจาก DOM)"""
    try:
        page.wait_for_selector(
            "#__UNIVERSAL_DATA_FOR_REHYDRATION__", state="attached", timeout=15000
        )
        raw = page.eval_on_selector(
            "#__UNIVERSAL_DATA_FOR_REHYDRATION__", "el => el.textContent"
        )
        info = json.loads(raw)["__DEFAULT_SCOPE__"]["webapp.user-detail"]["userInfo"]
    except Exception as e:
        logger.warning("อ่านข้อมูลโปรไฟล์จากหน้าไม่สำเร็จ: %s", e)
        return None

    user = info.get("user") or {}
    # statsV2 เป็นตัวเลขเต็ม (string) ส่วน stats เป็นตัวเลขปัดเศษ เช่น 96400000
    stats = {
        k: int(v) for k, v in (info.get("statsV2") or {}).items() if str(v).isdigit()
    } or info.get("stats") or {}
    if not user.get("uniqueId"):
        return None

    return {
        "unique_id": user.get("uniqueId"),
        "nickname": user.get("nickname"),
        "signature": user.get("signature"),
        "verified": user.get("verified"),
        "avatar": user.get("avatarMedium") or user.get("avatarThumb"),
        "bio_link": (user.get("bioLink") or {}).get("link"),
        "followers": stats.get("followerCount"),
        "following": stats.get("followingCount"),
        "total_likes": stats.get("heartCount"),
        "video_count": stats.get("videoCount"),
    }


def _wait_for_manual_captcha(page, items: list, label: str):
    """browser เปิดแบบมองเห็นได้ (headless=False) จึงรอให้คนเลื่อน captcha เองในหน้าต่าง Chrome"""
    logger.warning(
        "TikTok ขึ้น captcha (%s) — กรุณาเลื่อน slider ในหน้าต่าง Chrome ภายใน %d วินาที",
        label, CAPTCHA_WAIT_SECONDS,
    )
    for _ in range(CAPTCHA_WAIT_SECONDS):
        page.wait_for_timeout(1000)
        if items:
            return
        if _detect_block_reason(page) != "captcha":
            # แก้ captcha แล้ว รอ TikTok โหลดวิดีโอใหม่ ถ้ายังไม่มาให้ reload หน้า
            page.wait_for_timeout(3000)
            if not items:
                page.reload(wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
            return
    logger.warning("หมดเวลารอ captcha (%s)", label)


def scrape_channel(unique_id: str, max_videos: int = 20):
    """ดึงข้อมูลโปรไฟล์ + วิดีโอล่าสุดของช่อง คืน None ถ้าดึงโปรไฟล์ไม่ได้"""
    profile_url = _profile_url(unique_id)

    cached = get_cached("channel", profile_url)
    if cached and len(cached["videos"]) >= max_videos:
        return {**cached, "videos": cached["videos"][:max_videos]}

    items = []

    with sync_playwright() as playwright:
        browser = _launch_browser(playwright)
        context = _new_stealth_context(browser)
        page = context.new_page()
        page.route("**/*", _block_heavy_resources)

        def handle_response(response):
            if "/api/post/item_list/" in response.url:
                try:
                    items.extend(response.json().get("itemList") or [])
                except Exception:
                    pass

        page.on("response", handle_response)

        profile = None
        try:
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            profile = _extract_user_info(page)
            try:
                page.wait_for_selector('[data-e2e="user-post-item"]', timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(3000)

            if not items and _detect_block_reason(page) == "captcha":
                _wait_for_manual_captcha(page, items, unique_id)

            # เลื่อนหน้าลงเพื่อให้ TikTok โหลดวิดีโอเพิ่มจนได้ครบ max_videos
            for _ in range(3):
                if len(items) >= max_videos:
                    break
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(2500)
        except Exception as e:
            logger.warning("เปิดหน้าช่อง %s ไม่สำเร็จ: %s", unique_id, e)

        if profile is None or not items:
            reason = _detect_block_reason(page) or ("no_videos" if profile else "unknown")
            _save_debug_capture(page, unique_id, reason)

        browser.close()

    if profile is None:
        return None

    videos = []
    seen_ids = set()
    for item in items:
        video = _parse_item(item)
        if video["id"] and video["id"] not in seen_ids:
            seen_ids.add(video["id"])
            videos.append(video)
    videos.sort(key=lambda v: v.get("createTime") or 0, reverse=True)
    videos = videos[:max_videos]

    result = {"profile": profile, "videos": videos}
    if videos:
        set_cached(
            "channel", profile_url, result,
            unique_id=unique_id, followers=profile["followers"], videos_count=len(videos),
        )
    stats = {"followers": profile["followers"], "total_likes": profile["total_likes"]}
    set_cached("profile", profile_url, stats, unique_id=unique_id, **stats)
    return result
