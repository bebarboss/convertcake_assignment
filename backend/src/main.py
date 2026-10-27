from dotenv import load_dotenv

load_dotenv()

import asyncio
import logging
import sys
from typing import Optional
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

from cache import get_cached, set_cached
from channel_analyzer import analyze_channel, compute_channel_metrics
from tiktok_scraper import TOP_N, scrape_channel, scrape_tiktok
from top_analyzer import explain_top_results
from web_analyzer import analyze_urls
from browser_pool  import pool_manager, TooManyRequestsError

logger = logging.getLogger(__name__)

# uvicorn --reload บน Windows ตั้ง policy เป็น Selector ซึ่งเปิด subprocess ไม่ได้
# แต่ Playwright ต้องสร้าง loop ใหม่ใน thread ที่ scrape แล้วเปิด subprocess ของ driver
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

app = FastAPI(title="TikTok Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/search")
async def search_tiktok(
    keyword: list[str] = Query(..., description="research keyword"),
    top_n: Optional[int] = Query(TOP_N, ge=1, le=50, description="top10"),
    include_author_stats: bool = Query(
        True, description="รวมยอดผู้ติดตาม/ยอดไลค์รวมของ author เข้าในแต่ละวิดีโอด้วยไหม"
    ),
):
    # key = ลิงก์ของ request นี้ (เรียง keyword ให้ลำดับไม่มีผล)
    cache_key = "/search?" + urlencode(
        [("keyword", k) for k in sorted(keyword)]
        + [("top_n", top_n), ("include_author_stats", str(include_author_stats).lower())]
    )
    cached = await run_in_threadpool(get_cached, "search_result", cache_key)
    if cached:
        return {**cached, "from_cache": True}

    try:
        result = await pool_manager.run_scrape(
            scrape_tiktok, keyword, top_n, include_author_stats
        )
    except TooManyRequestsError as e:
        raise HTTPException(status_code=429, detail=str(e))

    if result is None:
        raise HTTPException(
            status_code=502,
            detail="ไม่พบผลการค้นหาจาก TikTok (อาจโดนบล็อก, cookie หมดอายุ, หรือ endpoint เปลี่ยน)",
        )

    response = {
        "keywords": keyword,
        "ai_summary": None,
        "videos_count": len(result["videos"]),
        "videos": result["videos"],
        "top_authors_count": len(result["top_authors"]),
        "top_authors": result["top_authors"],
    }

    try:
        analysis = await run_in_threadpool(
            explain_top_results, keyword, result["videos"], result["top_authors"]
        )
    except Exception as e:
        # AI ล้มเหลวก็ยังคืนผล scrape ได้ แต่ไม่เก็บลง db เพื่อให้ครั้งหน้าวิเคราะห์ใหม่
        logger.warning("AI วิเคราะห์ผล top ไม่สำเร็จ: %s", e)
        response["ai_warning"] = f"AI วิเคราะห์ไม่สำเร็จ: {e}"
        return {**response, "from_cache": False}

    response["ai_summary"] = analysis["summary"]
    for v in response["videos"]:
        v["ai_reason"] = analysis["videos"].get(str(v.get("id")))
    for a in response["top_authors"]:
        a["ai_reason"] = analysis["authors"].get(a.get("author_uniqueId"))

    await run_in_threadpool(
        set_cached, "search_result", cache_key, response,
        keywords=sorted(keyword), top_n=top_n, videos_count=len(response["videos"]),
    )
    return {**response, "from_cache": False}


@app.get("/analyze")
async def analyze(
    url: list[str] = Query(..., description="ลิงก์เว็บไซต์หรือ Facebook Page ของลูกค้า (ใส่ได้มากกว่า 1 ลิงก์)"),
    num_keywords: Optional[int] = Query(3, ge=1, le=5, description="จำนวน keyword ที่ให้ AI สร้าง"),
):
    try:
        result = await run_in_threadpool(analyze_urls, url, num_keywords)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not result.get("keywords"):
        raise HTTPException(
            status_code=502,
            detail=result.get("warning", "ไม่สามารถวิเคราะห์หน้าเว็บได้"),
        )

    return result


def _normalize_unique_id(value: str) -> str:
    """รับได้ทั้ง "name", "@name" หรือลิงก์ https://www.tiktok.com/@name"""
    value = value.strip()
    if "tiktok.com/@" in value:
        value = value.split("tiktok.com/@", 1)[1]
    return value.lstrip("@").split("/")[0].split("?")[0]


def _to_score(value):
    """AI อาจตอบคะแนนเป็น 9, "9" หรือ "9/10" แปลงเป็นตัวเลขสำหรับคอลัมน์ brand_fit_score"""
    try:
        return float(str(value).split("/")[0])
    except (TypeError, ValueError):
        return None


@app.get("/channel")
async def channel(
    unique_id: str = Query(..., description="uniqueId ของช่อง เช่น barista_a, @barista_a หรือลิงก์โปรไฟล์"),
    max_videos: Optional[int] = Query(20, ge=5, le=35, description="จำนวนวิดีโอล่าสุดที่ใช้วิเคราะห์"),
    context: Optional[str] = Query(None, description="ธุรกิจ/แบรนด์ของลูกค้า ใช้ประเมินความเหมาะสม (ไม่ใส่ก็ได้)"),
):
    uid = _normalize_unique_id(unique_id)
    if not uid:
        raise HTTPException(status_code=400, detail="unique_id ไม่ถูกต้อง")

    params = [("unique_id", uid), ("max_videos", max_videos)]
    if context:
        params.append(("context", context.strip()))
    cache_key = "/channel?" + urlencode(params)
    cached = await run_in_threadpool(get_cached, "channel_result", cache_key)
    if cached:
        return {**cached, "from_cache": True}

    try:
        result = await pool_manager.run_scrape(scrape_channel, uid, max_videos)
    except TooManyRequestsError as e:
        raise HTTPException(status_code=429, detail=str(e))

    if result is None:
        raise HTTPException(
            status_code=502,
            detail="ดึงข้อมูลช่องจาก TikTok ไม่ได้ (ไม่มีช่องนี้, โดนบล็อก หรือ cookie หมดอายุ)",
        )

    metrics = compute_channel_metrics(result["videos"])
    response = {
        "unique_id": uid,
        "profile_url": f"https://www.tiktok.com/@{uid}",
        "profile": result["profile"],
        "metrics": metrics,
        "ai_analysis": None,
        "videos": result["videos"],
    }

    if not result["videos"]:
        response["ai_warning"] = "ไม่พบวิดีโอของช่องนี้ (ช่องว่าง, ตั้งเป็นส่วนตัว หรือโดนบล็อก) จึงไม่ได้วิเคราะห์"
        return {**response, "from_cache": False}

    try:
        response["ai_analysis"] = await run_in_threadpool(
            analyze_channel, result["profile"], result["videos"], metrics, context
        )
    except Exception as e:
        logger.warning("AI วิเคราะห์ช่อง %s ไม่สำเร็จ: %s", uid, e)
        response["ai_warning"] = f"AI วิเคราะห์ไม่สำเร็จ: {e}"
        return {**response, "from_cache": False}

    await run_in_threadpool(
        set_cached, "channel_result", cache_key, response,
        unique_id=uid, context=context, max_videos=max_videos,
        brand_fit_score=_to_score(response["ai_analysis"].get("brand_fit_score")),
    )
    return {**response, "from_cache": False}


@app.get("/")
async def root():
    return {
        "message": "TikTok Search API",
        "endpoints": {
            "/channel?unique_id=...": "",
            "/search?keyword=...": "",
            "/analyze?url=...": "",
        },
    }


@app.get("/health")
async def health_check():
    in_use = pool_manager.max_concurrent_in_use()
    return {
        "status": "ok",
        "browsers_in_use": in_use,
        "max_concurrent_browsers": in_use + pool_manager.semaphore._value,
    }


@app.on_event("shutdown")
def shutdown_event():
    pool_manager.shutdown()