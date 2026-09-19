# ตารางเคสนอก / เคสใน (Flask + SQLite)

เว็บแอปให้ทุกคนเปิดดูผ่านลิงก์ได้ ส่วนการแก้ไขทำได้เฉพาะแอดมินที่ล็อกอิน
(ตรวจสิทธิ์ที่ฝั่งเซิร์ฟเวอร์ ไม่ใช่แค่ซ่อนปุ่ม) ข้อมูลเก็บในไฟล์ SQLite ผู้ชมทุกคนเห็นข้อมูลชุดเดียวกัน

## กติกา
- ทุกเดือนมีเคส 30 วันแรก วันละ 8 คนเคสใน (ปรับได้ในหน้าตั้งค่า)
- แต่ละคนได้ **เคสใน 15 วัน / เคสนอก 15 วัน** เท่ากันทุกเดือน
- วันที่ 31 เป็นวันพัก, เดือน ก.พ. (28 วัน) ได้ 14/14
- แอดมินกดที่ช่องในตารางเดือนเพื่อสลับเป็นรายกรณีได้

## รันในเครื่อง
```
python -m venv .venv
.venv\Scripts\activate        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py                 # เปิด http://localhost:5000
```
ล็อกอินเริ่มต้น: ID `admin` / Password `1234` (เปลี่ยนได้ในแท็บ "ตั้งค่า" หลังล็อกอิน)

## ตัวแปรสภาพแวดล้อม (ไม่บังคับ)
| ชื่อ | ความหมาย |
|---|---|
| `ADMIN_ID` | ID แอดมิน (ค่าเริ่มต้น `admin`) |
| `ADMIN_PASSWORD` | รหัสผ่านเริ่มต้น (ค่าเริ่มต้น `1234`) ถ้าเปลี่ยนรหัสในหน้าเว็บแล้ว รหัสในฐานข้อมูลจะมาก่อน |
| `SECRET_KEY` | กุญแจเซสชัน (ถ้าไม่ตั้ง จะสร้างและเก็บในฐานข้อมูลเอง) |
| `COOKIE_SECURE` | ตั้งเป็น `1` เมื่อเว็บเป็น https |
| `DATABASE_PATH` | ที่เก็บไฟล์ฐานข้อมูล (ค่าเริ่มต้น `data/case.db`) |

## เอาขึ้นเว็บให้คนนอกเข้าผ่านลิงก์

### ตัวเลือก A: PythonAnywhere (ฟรี เก็บข้อมูลถาวร เหมาะกับแอปเล็กแบบนี้)
1. สมัครที่ pythonanywhere.com เปิดแท็บ **Files** อัปโหลด `case-schedule-app.zip` แล้วแตกไฟล์ใน Bash console: `unzip case-schedule-app.zip`
2. ใน **Bash console**
   ```
   cd ~/case-app
   python3 -m venv ~/venv && source ~/venv/bin/activate
   pip install -r requirements.txt
   ```
3. แท็บ **Web** → Add a new web app → **Manual configuration** → เลือก Python 3.12 (หรือรุ่นที่มี)
4. ช่อง Virtualenv ใส่ `/home/<ชื่อผู้ใช้>/venv`
5. เปิดไฟล์ WSGI configuration แล้วแทนที่เนื้อหาทั้งหมดด้วย
   ```python
   import os, sys
   sys.path.insert(0, "/home/<ชื่อผู้ใช้>/case-app")
   os.environ["COOKIE_SECURE"] = "1"
   os.environ["ADMIN_PASSWORD"] = "ตั้งรหัสผ่านของคุณ"
   from app import app as application
   ```
6. กด **Reload** ลิงก์จะเป็น `https://<ชื่อผู้ใช้>.pythonanywhere.com`
   (บัญชีฟรีต้องกดปุ่มต่ออายุเว็บในแท็บ Web เป็นระยะ ตามที่เว็บแจ้ง)

### ตัวเลือก B: Render.com
1. อัปโหลดโค้ดขึ้น GitHub แล้วสร้าง Web Service (มี `render.yaml` ให้แล้ว)
2. ตั้ง `ADMIN_PASSWORD` ในหน้า Environment
3. ข้อควรระวัง: แพ็กเกจฟรีของ Render **ไม่มีดิสก์ถาวร** ไฟล์ฐานข้อมูลจะหายเมื่อรีสตาร์ต/ดีพลอยใหม่
   (ตารางที่คำนวณอัตโนมัติกลับเป็นค่าเริ่มต้น เฉพาะสิ่งที่แอดมินแก้ไว้จะหาย)
   ถ้าต้องการข้อมูลถาวร ให้ใช้แพ็กเกจที่เพิ่ม Disk แล้วตั้ง `DATABASE_PATH=/var/data/case.db`

### ตัวเลือก C: VPS / เครื่องของตัวเอง
```
pip install -r requirements.txt
COOKIE_SECURE=1 ADMIN_PASSWORD=รหัสของคุณ gunicorn app:app --workers 2 --bind 0.0.0.0:8000
```
แล้วใส่ nginx หรือ Cloudflare Tunnel ด้านหน้าเพื่อให้เป็น https

## ความปลอดภัย
- รหัสผ่านตรวจที่ฝั่งเซิร์ฟเวอร์และเก็บเป็นแฮช ไม่อยู่ในโค้ดที่ผู้ชมโหลดไป มีจำกัดการเดารหัส (ผิดเกิน 8 ครั้ง รอ 5 นาที)
- **เปลี่ยนรหัส `1234` ทันทีหลังขึ้นเว็บจริง** (แท็บ ตั้งค่า → เปลี่ยนรหัสผ่านแอดมิน หรือตั้ง `ADMIN_PASSWORD`)
- ใช้ https เสมอเมื่อเปิดสาธารณะ และตั้ง `COOKIE_SECURE=1`
