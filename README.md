# TikTok Insight

ระบบช่วยหาครีเอเตอร์ TikTok ที่เหมาะกับธุรกิจของลูกค้า ใส่ลิงก์เว็บหรือเพจ Facebook ของลูกค้า แล้วระบบจะให้ AI สรุปเป็น keyword ค้น TikTok หาวิดีโอและครีเอเตอร์ที่เด่น และวิเคราะห์ช่องที่สนใจพร้อมให้คะแนนความเหมาะสมกับแบรนด์

| ส่วน | เทคโนโลยี | โฟลเดอร์ |
|---|---|---|
| Frontend | React 19, TanStack Start, Tailwind 4, shadcn/ui, Vite | `frontend/` |
| Backend | FastAPI, Playwright (Chromium), Typhoon LLM | `backend/` |
| Cache (ไม่บังคับ) | Supabase | `backend/supabase/schema.sql` |

รายละเอียดการทำงาน API และ troubleshooting ดูที่ [docs/manual.md](docs/manual.md) และ diagram ที่ [docs/diagrams.md](docs/diagrams.md)

---

## สิ่งที่ต้องมี

- Python 3.11 ขึ้นไป
- Node.js 20.19 ขึ้นไป (หรือ 22.12+) พร้อม npm
- API key ของ [Typhoon](https://opentyphoon.ai)
- `cookies.json` ของบัญชี TikTok ที่ login แล้ว (ดูหัวข้อ [Cookies](#cookies-ของ-tiktok))
- เครื่องที่มีหน้าจอ เพราะ backend เปิด Chrome แบบ `headless=False`
- (ไม่บังคับ) โปรเจกต์ Supabase สำหรับ cache
- (ไม่บังคับ) Docker Desktop ถ้าจะรันผ่าน Docker

---

## การติดตั้ง

### 1. Clone

```bash
git clone https://github.com/bebarboss/convertcake_assignment.git
cd convertcake_assignment
```

### 2. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate          # macOS / Linux: source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

ตั้งค่า environment:

```powershell
copy .env.example .env           # macOS / Linux: cp .env.example .env
```

แล้วแก้ `backend/.env` อย่างน้อยต้องใส่ `TYPHOON_API_KEY` ตัวแปรอื่นดูคำอธิบายได้ใน [.env.example](backend/.env.example)

### 3. Cookies ของ TikTok

1. login TikTok ใน Chrome
2. ใช้ extension เช่น Cookie-Editor export cookies ของ `tiktok.com` เป็น JSON
3. บันทึกเป็น `backend/cookies.json`

ถ้าไม่มีไฟล์นี้ระบบยังรันได้ แต่มีโอกาสโดน TikTok บล็อกสูงมาก ถ้า `/search` เริ่มได้ 502 ให้ export cookies ใหม่

### 4. Supabase (ไม่บังคับ)

1. สร้างโปรเจกต์ใน Supabase
2. เปิด SQL Editor แล้วรัน [backend/supabase/schema.sql](backend/supabase/schema.sql)
3. ใส่ `SUPABASE_URL` และ `SUPABASE_KEY` (service_role key) ใน `backend/.env`

ถ้าไม่ตั้งค่า ระบบทำงานได้ตามปกติแต่ไม่มี cache

### 5. Frontend

```bash
cd frontend
npm install
```

---

## การรัน

### Local

เปิด 2 terminal

**Terminal 1: backend** (ต้องรันจากโฟลเดอร์ `backend` เพื่อให้หา `.env` และ `cookies.json` เจอ)

```powershell
cd backend
.\venv\Scripts\activate
python -m uvicorn main:app --app-dir src --port 8000
```

ตรวจว่า backend ทำงาน: เปิด http://127.0.0.1:8000/docs (Swagger UI)

**Terminal 2: frontend**

```bash
cd frontend
npm run dev
```

เปิด http://localhost:5173 ตัว Vite จะ proxy `/api/*` ไปที่ `http://127.0.0.1:8000` ถ้า backend อยู่ที่อื่นให้ตั้ง env `API_BASE` ก่อนรัน เช่น

```powershell
$env:API_BASE="https://xxxx.ngrok-free.app"; npm run dev
```

ระหว่างที่ `/channel` ทำงานอาจเจอ captcha ให้เลื่อน slider เองในหน้าต่าง Chrome ที่ backend เปิดขึ้นมา (รอได้ `CAPTCHA_WAIT_SECONDS` วินาที)

### Docker (backend + ngrok)

```powershell
cd backend
docker compose up -d --build
```

- ต้องมี `backend/.env` และ `backend/cookies.json` ก่อนรัน (compose mount `cookies.json` แบบ read-only)
- backend อยู่ที่ http://localhost:8000 และ URL สาธารณะของ ngrok ดูได้ที่ http://localhost:4040
- ถ้าไม่ใช้ ngrok รันเฉพาะ backend ได้ด้วย `docker compose up -d --build app`
- ใน container ไม่มีใครเลื่อน captcha ได้ ควรตั้ง `CAPTCHA_WAIT_SECONDS=0`

หยุดการทำงาน: `docker compose down`

### Deploy frontend บน Vercel

1. import โฟลเดอร์ `frontend` เป็นโปรเจกต์ใน Vercel (`vercel.json` ตั้งค่า build ไว้แล้ว)
2. ตั้ง environment variable `API_BASE` เป็น URL สาธารณะของ backend (เช่น URL ของ ngrok)
3. deploy

---

## API

| Endpoint | ทำอะไร |
|---|---|
| `GET /analyze?url=...` | อ่านเว็บลูกค้าแล้วสร้าง keyword |
| `GET /search?keyword=...` | ค้น TikTok หาวิดีโอและครีเอเตอร์เด่น |
| `GET /channel?unique_id=...` | วิเคราะห์ช่อง TikTok และ brand fit |

parameter ทั้งหมดดูได้ที่ http://127.0.0.1:8000/docs หรือ [docs/manual.md](docs/manual.md#3-api-reference)
