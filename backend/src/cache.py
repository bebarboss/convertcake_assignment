import logging
import os
from datetime import datetime, timedelta, timezone

from supabase import create_client

logger = logging.getLogger(__name__)

CACHE_TTL = timedelta(days=2)

# kind -> (ชื่อ table, คอลัมน์ที่เป็น key) ดูโครงสร้างได้ที่ supabase/schema.sql
TABLES = {
    "page": ("web_pages", "url"),
    "search": ("tiktok_searches", "search_url"),
    "profile": ("tiktok_profiles", "profile_url"),
    "channel": ("tiktok_channels", "profile_url"),
    "search_result": ("search_results", "request_key"),
    "channel_result": ("channel_analyses", "request_key"),
}

_client = None


def _get_client():
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            return None
        _client = create_client(url, key)
    return _client


def get_cached(kind: str, key: str):
    """คืนข้อมูลที่เคยเก็บไว้ของ key นี้ ถ้ายังไม่เกิน CACHE_TTL ไม่งั้นคืน None"""
    client = _get_client()
    if client is None:
        return None

    table, key_column = TABLES[kind]
    cutoff = (datetime.now(timezone.utc) - CACHE_TTL).isoformat()
    try:
        res = (
            client.table(table)
            .select("data")
            .eq(key_column, key)
            .gte("created_at", cutoff)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.warning("อ่าน cache จาก Supabase ไม่สำเร็จ (%s %s): %s", table, key, e)
        return None

    if res.data:
        logger.info("ใช้ข้อมูลจาก cache: %s %s", table, key)
        return res.data[0]["data"]
    return None


def set_cached(kind: str, key: str, data, **columns):
    """บันทึก data (jsonb) ลง table ของ kind นี้ columns คือคอลัมน์เสริมสำหรับ query เช่น unique_id"""
    client = _get_client()
    if client is None:
        return

    table, key_column = TABLES[kind]
    try:
        client.table(table).upsert(
            {
                key_column: key,
                **columns,
                "data": data,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict=key_column,
        ).execute()
    except Exception as e:
        logger.warning("บันทึก cache ลง Supabase ไม่สำเร็จ (%s %s): %s", table, key, e)
