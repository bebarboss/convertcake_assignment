# Diagrams

## 1. Architecture

```mermaid
flowchart LR
    U["ผู้ใช้ (Browser)"] --> FE["Frontend<br/>React + TanStack Start<br/>Vercel"]
    FE -->|"/api/analyze<br/>/api/search<br/>/api/channel"| PX["Vercel Functions<br/>frontend/api/*.js<br/>proxy"]
    PX -->|"API_BASE"| BE["Backend FastAPI<br/>backend/src/main.py<br/>Docker"]

    BE --> POOL["BrowserPoolManager<br/>browser_pool.py"]
    POOL --> PW["Playwright Chromium"]
    PW --> TT["TikTok"]
    BE --> WA["web_analyzer.py"] --> PW2["Playwright Chromium"] --> WEB["เว็บ / Facebook ลูกค้า"]
    BE --> LLM["llm.py"] --> TY["Typhoon LLM API"]
    BE --> CA["cache.py"] --> SB[("Supabase")]
```

## 2. User flow (3 ขั้น)

```mermaid
sequenceDiagram
    actor U as ผู้ใช้
    participant FE as Frontend
    participant BE as Backend
    participant AI as Typhoon LLM

    U->>FE: ใส่ลิงก์เว็บ / เพจลูกค้า
    FE->>BE: GET /analyze?url=...&num_keywords=5
    BE->>BE: เปิดหน้าเว็บ ดึง title / description / text
    BE->>AI: สร้าง keyword ภาษาไทย
    AI-->>BE: ["keyword", ...]
    BE-->>FE: page_contents + keywords

    U->>FE: เลือก keyword แล้วกดค้นหา
    FE->>BE: GET /search?keyword=...&top_n=10
    BE->>BE: scrape TikTok หา top videos + top authors
    BE->>AI: อธิบายว่าทำไมติดอันดับ
    AI-->>BE: summary + เหตุผลรายวิดีโอ / ราย author
    BE-->>FE: videos + top_authors + ai_summary

    U->>FE: กดวิเคราะห์ช่องของ author
    FE->>BE: GET /channel?unique_id=...&max_videos=20&context=...
    BE->>BE: scrape โปรไฟล์ + วิดีโอล่าสุด, คำนวณ metrics
    BE->>AI: วิเคราะห์ช่อง + brand fit
    AI-->>BE: ai_analysis
    BE-->>FE: profile + metrics + ai_analysis + videos
```

## 3. /search

```mermaid
flowchart TD
    A["GET /search"] --> B{"cache search_results<br/>ยังไม่เกิน 2 วัน?"}
    B -->|มี| Z1["คืนผล from_cache=true"]
    B -->|ไม่มี| C{"คิวเกิน 10?"}
    C -->|ใช่| E429["429 Too Many Requests"]
    C -->|ไม่| D["pool_manager.run_scrape<br/>รอ slot ว่าง (max 3)"]
    D --> F["ทุก keyword:<br/>cache tiktok_searches?"]
    F -->|ไม่มี| G["เปิด TikTok search<br/>ดัก api/search/general/full/"]
    G -->|ไม่ได้ข้อมูล| DBG["บันทึก debug_captures"]
    G --> H["รวมวิดีโอ ตัดซ้ำ"]
    F -->|มี| H
    H --> I{"มีวิดีโอ?"}
    I -->|ไม่| E502["502"]
    I -->|มี| J["top videos ตามยอดไลค์"]
    J --> K["ดึง followers / total_likes ของ author<br/>cache tiktok_profiles"]
    K --> L["top authors ตาม followers"]
    L --> M["explain_top_results (AI)"]
    M -->|สำเร็จ| N["บันทึก search_results"] --> Z2["คืนผล"]
    M -->|ล้มเหลว| W["คืนผล + ai_warning<br/>ไม่บันทึก cache"]
```

## 4. /channel

```mermaid
flowchart TD
    A["GET /channel"] --> B["normalize unique_id<br/>@name / ลิงก์ → name"]
    B --> C{"cache channel_analyses?"}
    C -->|มี| Z1["คืนผล from_cache=true"]
    C -->|ไม่มี| D{"cache tiktok_channels<br/>มีวิดีโอพอ?"}
    D -->|มี| G
    D -->|ไม่มี| E["เปิดหน้าโปรไฟล์<br/>อ่าน __UNIVERSAL_DATA_FOR_REHYDRATION__<br/>ดัก /api/post/item_list/"]
    E --> CAP{"เจอ captcha?"}
    CAP -->|ใช่| WAIT["รอคนแก้เอง<br/>CAPTCHA_WAIT_SECONDS"] --> SC
    CAP -->|ไม่| SC["scroll โหลดวิดีโอเพิ่ม"]
    SC --> F{"ได้ profile?"}
    F -->|ไม่| E502["502"]
    F -->|ได้| G["compute_channel_metrics"]
    G --> H{"มีวิดีโอ?"}
    H -->|ไม่| W1["คืนผล + ai_warning"]
    H -->|มี| I["analyze_channel (AI)<br/>+ context ของลูกค้า"]
    I -->|สำเร็จ| J["บันทึก channel_analyses<br/>+ brand_fit_score"] --> Z2["คืนผล"]
    I -->|ล้มเหลว| W2["คืนผล + ai_warning"]
```

## 5. Cache (Supabase)

```mermaid
flowchart LR
    subgraph raw["ข้อมูลดิบ"]
        P["web_pages<br/>key: url"]
        S["tiktok_searches<br/>key: search_url"]
        PR["tiktok_profiles<br/>key: profile_url"]
        CH["tiktok_channels<br/>key: profile_url"]
    end
    subgraph result["ผลลัพธ์ที่ AI วิเคราะห์แล้ว"]
        SR["search_results<br/>key: request_key"]
        CR["channel_analyses<br/>key: request_key"]
    end

    AN["/analyze"] --> P
    SE["/search"] --> S & PR & SR
    CN["/channel"] --> CH & PR & CR
```

ทุกตารางหมดอายุ 2 วัน (`CACHE_TTL`) ถ้าไม่ได้ตั้ง `SUPABASE_URL` / `SUPABASE_KEY` จะข้าม cache ทั้งหมด
