-- โครงสร้าง db ของ TikTok Search API (รันใน Supabase SQL Editor)
-- ทุก table: key + คอลัมน์สำหรับ query + data (jsonb ข้อมูลเต็มที่ API ใช้) + created_at
-- ข้อมูลมีอายุ 2 วัน (แอปไม่อ่านข้อมูลที่เก่ากว่านั้น และ cron ลบทิ้งทุกชั่วโมง)

-- ── ข้อมูลดิบจากการ scrape ─────────────────────────────────────────────

-- เนื้อหาหน้าเว็บ/เพจลูกค้าที่ /analyze เปิดอ่าน
create table if not exists public.web_pages (
  url        text primary key,
  title      text,
  data       jsonb       not null,
  created_at timestamptz not null default now()
);

-- ผลค้นหา TikTok ต่อ 1 keyword
create table if not exists public.tiktok_searches (
  search_url   text primary key,
  keyword      text,
  videos_count int,
  data         jsonb       not null,
  created_at   timestamptz not null default now()
);

-- ยอดผู้ติดตาม/ยอดไลค์รวมของช่อง
create table if not exists public.tiktok_profiles (
  profile_url text primary key,
  unique_id   text,
  followers   bigint,
  total_likes bigint,
  data        jsonb       not null,
  created_at  timestamptz not null default now()
);

-- โปรไฟล์เต็ม + วิดีโอล่าสุดของช่อง (ใช้โดย /channel)
create table if not exists public.tiktok_channels (
  profile_url  text primary key,
  unique_id    text,
  followers    bigint,
  videos_count int,
  data         jsonb       not null,
  created_at   timestamptz not null default now()
);

-- ── ผลลัพธ์ที่ AI วิเคราะห์แล้ว (key = ลิงก์ของ request) ────────────────

-- ผลลัพธ์ของ /search พร้อม ai_summary / ai_reason
create table if not exists public.search_results (
  request_key  text primary key,
  keywords     text[],
  top_n        int,
  videos_count int,
  data         jsonb       not null,
  created_at   timestamptz not null default now()
);

-- ผลลัพธ์ของ /channel พร้อม ai_analysis
create table if not exists public.channel_analyses (
  request_key     text primary key,
  unique_id       text,
  context         text,
  max_videos      int,
  brand_fit_score numeric,
  data            jsonb       not null,
  created_at      timestamptz not null default now()
);

create index if not exists tiktok_profiles_unique_id_idx  on public.tiktok_profiles (unique_id);
create index if not exists tiktok_channels_unique_id_idx  on public.tiktok_channels (unique_id);
create index if not exists channel_analyses_unique_id_idx on public.channel_analyses (unique_id);

-- เปิด RLS โดยไม่มี policy = เข้าถึงได้เฉพาะ secret / service_role key เท่านั้น
alter table public.web_pages        enable row level security;
alter table public.tiktok_searches  enable row level security;
alter table public.tiktok_profiles  enable row level security;
alter table public.tiktok_channels  enable row level security;
alter table public.search_results   enable row level security;
alter table public.channel_analyses enable row level security;

-- ลบข้อมูลที่เก่ากว่า 2 วันทุกชั่วโมง
create extension if not exists pg_cron;

select cron.schedule(
  'purge-cache',
  '0 * * * *',
  $$
  delete from public.web_pages        where created_at < now() - interval '2 days';
  delete from public.tiktok_searches  where created_at < now() - interval '2 days';
  delete from public.tiktok_profiles  where created_at < now() - interval '2 days';
  delete from public.tiktok_channels  where created_at < now() - interval '2 days';
  delete from public.search_results   where created_at < now() - interval '2 days';
  delete from public.channel_analyses where created_at < now() - interval '2 days';
  $$
);
