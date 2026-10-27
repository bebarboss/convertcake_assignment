import json

from playwright.sync_api import sync_playwright

from cache import get_cached, set_cached
from llm import chat


def extract_page_content(browser, url: str, max_chars: int = 4000):
    context = browser.new_context(locale="th-TH")
    page = context.new_page()

    content = {"title": None, "description": None, "text": None, "url": url}

    try:
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

        content["title"] = page.title()

        meta_desc = page.query_selector('meta[name="description"]')
        og_desc = page.query_selector('meta[property="og:description"]')
        content["description"] = (
            (meta_desc.get_attribute("content") if meta_desc else None)
            or (og_desc.get_attribute("content") if og_desc else None)
        )

        body_text = page.inner_text("body")
        content["text"] = body_text[:max_chars] if body_text else None

    except Exception as e:
        content["error"] = str(e)
    finally:
        context.close()
    return content


def generate_tiktok_keywords(page_contents: list, num_keywords: int = 5):
    pages_text = []
    for i, pc in enumerate(page_contents, start=1):
        section = "\n".join(filter(None, [
            f"--- ลิงก์ที่ {i}: {pc.get('url')} ---",
            f"Title: {pc.get('title')}",
            f"Description: {pc.get('description')}",
            f"Page text (บางส่วน): {pc.get('text')}",
        ]))
        pages_text.append(section)

    combined_text = "\n\n".join(pages_text)

    prompt = f"""จากเนื้อหาหน้าเว็บ/เพจ Facebook ของลูกค้าด้านล่างนี้ (อาจมีมากกว่า 1 ลิงก์
มาจากธุรกิจเดียวกัน) ช่วยสรุปเป็น keyword ภาษาไทยสั้นๆ จำนวน {num_keywords} คำ
ที่เหมาะสำหรับเอาไปค้นหาใน TikTok เพื่อหาคอนเทนต์/กลุ่มเป้าหมายที่เกี่ยวข้องกับธุรกิจนี้

ตอบกลับเป็น JSON array ของ string เท่านั้น ห้ามมีคำอธิบายอื่นใดๆ
เช่น ["คำที่ 1", "คำที่ 2", "คำที่ 3"]

เนื้อหา:
{combined_text}
"""

    cleaned = chat(prompt, max_tokens=300)

    try:
        keywords = json.loads(cleaned)
        if isinstance(keywords, list):
            return [str(k).strip() for k in keywords if k]
    except json.JSONDecodeError:
        pass

    fallback = [k.strip(' "-') for k in cleaned.replace("\n", ",").split(",") if k.strip()]
    return fallback[:num_keywords]


def analyze_urls(urls: list, num_keywords: int = 3):
    page_contents = [get_cached("page", url) for url in urls]
    missing = [i for i, pc in enumerate(page_contents) if pc is None]

    if missing:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            for i in missing:
                pc = extract_page_content(browser, urls[i])
                if not pc.get("error") and (pc.get("title") or pc.get("text")):
                    set_cached("page", urls[i], pc, title=pc.get("title"))
                page_contents[i] = pc
            browser.close()

    valid_contents = [pc for pc in page_contents if pc.get("title") or pc.get("text")]

    if not valid_contents:
        return {
            "page_contents": page_contents,
            "keywords": [],
            "warning": "ดึงเนื้อหาจากทุกลิงก์ไม่ได้เลย (อาจต้อง login หรือหน้าใช้ JS หนักเกินไป)",
        }

    keywords = generate_tiktok_keywords(valid_contents, num_keywords=num_keywords)

    if not keywords:
        return {
            "page_contents": page_contents,
            "keywords": [],
            "warning": "AI สร้าง keyword ไม่สำเร็จ",
        }

    return {
        "page_contents": [
            {"url": pc.get("url"), "title": pc.get("title"), "description": pc.get("description"), "text": pc.get("text")}
            for pc in page_contents
        ],
        "keywords": keywords,
    }