import json
from collections import Counter
from datetime import datetime, timezone
from statistics import median

from llm import chat
from top_analyzer import _engagement_rate


def compute_channel_metrics(videos: list):
    """คำนวณตัวเลขของช่องจากวิดีโอล่าสุด (คิดเองไม่ให้ AI คำนวณ เพื่อให้ตัวเลขถูกต้อง)"""
    if not videos:
        return {"videos_analyzed": 0}

    stats = [v.get("stats") or {} for v in videos]
    plays = [s.get("plays") or 0 for s in stats]
    likes = [s.get("likes") or 0 for s in stats]
    rates = [r for r in (_engagement_rate(s) for s in stats) if r is not None]
    times = sorted(v["createTime"] for v in videos if v.get("createTime"))

    posts_per_week = None
    latest_post_date = None
    days_since_last_post = None
    if times:
        now = datetime.now(timezone.utc).timestamp()
        latest_post_date = datetime.fromtimestamp(times[-1], timezone.utc).date().isoformat()
        days_since_last_post = int((now - times[-1]) // 86400)
        span_days = (times[-1] - times[0]) / 86400
        if len(times) > 1 and span_days > 0:
            posts_per_week = round(len(times) / span_days * 7, 1)

    hashtag_counts = Counter(
        tag.lower() for v in videos for tag in (v.get("hashtags") or [])
    )

    return {
        "videos_analyzed": len(videos),
        "avg_plays": int(sum(plays) / len(plays)),
        "median_plays": int(median(plays)),
        "max_plays": max(plays),
        "avg_likes": int(sum(likes) / len(likes)),
        "avg_engagement_rate_percent": round(sum(rates) / len(rates), 2) if rates else None,
        "posts_per_week": posts_per_week,
        "latest_post_date": latest_post_date,
        "days_since_last_post": days_since_last_post,
        "top_hashtags": [
            {"tag": tag, "count": count} for tag, count in hashtag_counts.most_common(10)
        ],
    }


def analyze_channel(profile: dict, videos: list, metrics: dict, context: str | None = None):
    today = datetime.now(timezone.utc).date().isoformat()

    video_samples = [
        {
            "desc": (v.get("desc") or "")[:150],
            "hashtags": (v.get("hashtags") or [])[:8],
            "created_date": (
                datetime.fromtimestamp(v["createTime"], timezone.utc).date().isoformat()
                if v.get("createTime") else None
            ),
            "stats": v.get("stats"),
            "engagement_rate_percent": _engagement_rate(v.get("stats") or {}),
        }
        for v in videos
    ]

    data = {"profile": profile, "metrics": metrics, "recent_videos": video_samples}

    brand_part = (
        f"ธุรกิจ/แบรนด์ของลูกค้า: {context}\nให้ประเมินด้วยว่าช่องนี้เหมาะกับแบรนด์นี้แค่ไหน"
        if context else
        "ไม่มีข้อมูลแบรนด์ของลูกค้า ให้ประเมินว่าช่องนี้เหมาะกับแบรนด์ประเภทไหน"
    )

    prompt = f"""คุณเป็นนักวิเคราะห์ influencer marketing บน TikTok
วันนี้คือวันที่ {today}
วิเคราะห์ช่อง TikTok ด้านล่างจากข้อมูลโปรไฟล์ ตัวเลขสรุป (metrics) และวิดีโอล่าสุด
{brand_part}

อ้างอิงตัวเลขจริงจากข้อมูล ห้ามแต่งตัวเลขขึ้นเอง ใช้ภาษาไทยเท่านั้น (ห้ามมีภาษาจีน)

ตอบกลับเป็น JSON object เท่านั้น ห้ามมีคำอธิบายอื่นใดๆ ตามรูปแบบนี้
{{
  "summary": "ภาพรวมของช่อง 2-3 ประโยค",
  "content_themes": ["แนวคอนเทนต์หลัก", "..."],
  "posting_behavior": "ความถี่และความสม่ำเสมอในการโพสต์ ยังแอคทีฟอยู่ไหม",
  "performance": "ยอดวิว/engagement เทียบกับยอดผู้ติดตาม คลิปไหนแนวไหนได้ผลดี",
  "audience": "กลุ่มผู้ชมที่น่าจะเป็น",
  "strengths": ["..."],
  "concerns": ["ข้อควรระวัง เช่น ยอดวิวไม่สม่ำเสมอ หยุดโพสต์ คอนเทนต์ไม่ตรงแบรนด์"],
  "brand_fit": "ความเหมาะสมกับแบรนด์",
  "brand_fit_score": <คะแนน 1-10>,
  "collaboration_ideas": ["ไอเดียรูปแบบการร่วมงาน", "..."]
}}

ข้อมูล:
{json.dumps(data, ensure_ascii=False)}
"""

    cleaned = chat(prompt, max_tokens=3000)

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("AI ไม่ได้ตอบกลับเป็น JSON")
    return json.loads(cleaned[start:end + 1])
