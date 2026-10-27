import json
from datetime import datetime, timezone

from llm import chat


def _engagement_rate(stats: dict):
    plays = stats.get("plays") or 0
    if not plays:
        return None
    interactions = sum((stats.get(k) or 0) for k in ("likes", "comments", "shares"))
    return round(interactions / plays * 100, 2)


def _compact_video(v: dict):
    stats = v.get("stats") or {}
    created = v.get("createTime")
    return {
        "id": v.get("id"),
        "desc": (v.get("desc") or "")[:200],
        "hashtags": (v.get("hashtags") or [])[:10],
        "author_uniqueId": v.get("author_uniqueId"),
        "author_followers": v.get("author_followers"),
        "created_date": (
            datetime.fromtimestamp(created, timezone.utc).date().isoformat()
            if created else None
        ),
        "stats": stats,
        "engagement_rate_percent": _engagement_rate(stats),
    }


def _compact_author(a: dict):
    return {
        "author_uniqueId": a.get("author_uniqueId"),
        "author_name": a.get("author_name"),
        "followers": a.get("followers"),
        "total_likes": a.get("total_likes"),
        "top_video_likes": a.get("top_likes"),
    }


def explain_top_results(keywords: list, videos: list, top_authors: list):
    """ให้ AI อธิบายว่าทำไมวิดีโอ/ครีเอเตอร์แต่ละรายการถึงติดอันดับ

    คืน {"summary": str, "videos": {id: reason}, "authors": {uniqueId: reason}}
    """
    data = {
        "videos": [_compact_video(v) for v in videos],
        "top_authors": [_compact_author(a) for a in top_authors],
    }

    today = datetime.now(timezone.utc).date().isoformat()

    # ใส่ id ครบทุกรายการไว้ในโครงคำตอบ ไม่งั้น AI มักตอบแค่ 5 รายการแรก
    template = json.dumps({
        "summary": "สรุปภาพรวมว่าคอนเทนต์แบบไหนได้ผลดีสำหรับ keyword นี้ 2-4 ประโยค",
        "videos": [{"id": str(v.get("id")), "reason": "..."} for v in videos],
        "authors": [{"author_uniqueId": a.get("author_uniqueId"), "reason": "..."} for a in top_authors],
    }, ensure_ascii=False, indent=2)

    prompt = f"""คุณเป็นนักวิเคราะห์การตลาดบน TikTok
วันนี้คือวันที่ {today}
ด้านล่างคือผลการค้นหา TikTok ด้วย keyword: {", ".join(keywords)}

เกณฑ์ที่ระบบใช้เลือก:
- videos: เรียงตามยอดไลค์มากที่สุด
- top_authors: เรียงตามยอดผู้ติดตาม แล้วตามยอดไลค์ของวิดีโอที่ดีที่สุด

ช่วยวิเคราะห์เป็นภาษาไทยว่าแต่ละรายการติดอันดับ/น่าสนใจเพราะอะไร
โดยอ้างอิงตัวเลขจริง เช่น ยอดไลค์ ยอดวิว engagement rate ยอดผู้ติดตาม
ความเกี่ยวข้องกับ keyword หัวข้อหรือ hashtag ที่ใช้ และความสดใหม่ของคลิป
แต่ละ reason ยาวไม่เกิน 2 ประโยค ใช้ภาษาไทยเท่านั้น (ห้ามมีภาษาจีน)
ต้องเขียน reason ครบทุกรายการ: วิดีโอ {len(videos)} รายการ และ author {len(top_authors)} รายการ ห้ามข้ามหรือตัดรายการใดออก

ตอบกลับเป็น JSON object เท่านั้น ห้ามมีคำอธิบายอื่นใดๆ ใช้โครงด้านล่างนี้ แทนที่ "..." ด้วยเหตุผล และห้ามแก้ id
{template}

ข้อมูล:
{json.dumps(data, ensure_ascii=False)}
"""

    max_tokens = min(8000, 600 + 250 * (len(videos) + len(top_authors)))
    cleaned = chat(prompt, max_tokens=max_tokens)

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AI ไม่ได้ตอบกลับเป็น JSON")
    parsed = json.loads(cleaned[start:end + 1])

    return {
        "summary": parsed.get("summary"),
        "videos": {
            str(v.get("id")): v.get("reason")
            for v in parsed.get("videos") or [] if v.get("id") and v.get("reason") not in (None, "", "...")
        },
        "authors": {
            v.get("author_uniqueId"): v.get("reason")
            for v in parsed.get("authors") or [] if v.get("author_uniqueId") and v.get("reason") not in (None, "", "...")
        },
    }
