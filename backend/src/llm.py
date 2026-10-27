import os

from openai import OpenAI

TYPHOON_API_BASE = os.getenv("TYPHOON_API_BASE", "https://api.opentyphoon.ai/v1")
TYPHOON_MODEL = os.getenv("TYPHOON_MODEL", "typhoon-v2.5-30b-a3b-instruct")


def chat(prompt: str, max_tokens: int) -> str:
    """ส่ง prompt ไปที่ Typhoon แล้วคืนข้อความตอบกลับที่ตัด ```json ออกแล้ว"""
    api_key = os.environ.get("TYPHOON_API_KEY")
    if not api_key:
        raise RuntimeError("ไม่พบ TYPHOON_API_KEY ใน environment variable")

    client = OpenAI(api_key=api_key, base_url=TYPHOON_API_BASE)

    response = client.chat.completions.create(
        model=TYPHOON_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = (response.choices[0].message.content or "").strip()
    return raw_text.replace("```json", "").replace("```", "").strip()
