
import asyncio
import json
import logging
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
import zipfile
import os
from telethon import TelegramClient
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ملف الإعدادات
settings_file = "settings.json"

# تخزين العملاء والجلسات
clients = {}
sessions = {}

def load_settings():
    """تحميل الإعدادات من الملف"""
    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {
            "api_id": "22043994",
            "api_hash": "56f64582b363d367280db96586b97801",
            "phone": "",
            "is_logged": False,
            "message": "مرحبا 👋 هذا إعلان تجريبي",
            "groups": [],
            "interval": 30,
            "is_sending": False
        }

def save_settings(data):
    """حفظ الإعدادات في الملف"""
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """الصفحة الرئيسية"""
    settings = load_settings()
    return templates.TemplateResponse("index.html", {"request": request, "settings": settings})

@app.post("/save")
async def save_config(
    api_id: str = Form(...), 
    api_hash: str = Form(...), 
    phone: str = Form(...),
    message: str = Form(...), 
    groups: str = Form(...), 
    interval: int = Form(...)
):
    """حفظ إعدادات البوت"""
    settings = load_settings()
    settings.update({
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "message": message,
        "groups": [g.strip() for g in groups.splitlines() if g.strip()],
        "interval": interval
    })
    save_settings(settings)
    return RedirectResponse("/", status_code=303)

@app.post("/request_code")
async def request_code():
    """طلب رمز التحقق"""
    settings = load_settings()
    phone = settings.get("phone")
    api_id = settings.get("api_id")
    api_hash = settings.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        return JSONResponse({"status": "error", "message": "❌ يرجى تعبئة جميع البيانات أولاً"})
    
    try:
        client = TelegramClient(f"session_{phone}", int(api_id), api_hash)
        await client.connect()
        
        if not await client.is_user_authorized():
            sent = await client.send_code_request(phone)
            sessions[phone] = {
                "client": client, 
                "phone_code_hash": sent.phone_code_hash
            }
            await client.disconnect()
            return JSONResponse({"status": "ok", "message": "✅ تم إرسال الكود إلى تليجرام"})
        else:
            settings["is_logged"] = True
            save_settings(settings)
            await client.disconnect()
            return JSONResponse({"status": "ok", "message": "✅ أنت مسجل دخول بالفعل"})
            
    except Exception as e:
        logger.error(f"خطأ في طلب الكود: {e}")
        return JSONResponse({"status": "error", "message": f"❌ خطأ: {str(e)}"})

@app.post("/verify_code")
async def verify_code(code: str = Form(...)):
    """تأكيد رمز التحقق"""
    settings = load_settings()
    phone = settings.get("phone")
    
    session = sessions.get(phone)
    if not session:
        return JSONResponse({"status": "error", "message": "❌ يرجى طلب الكود أولاً"})
    
    try:
        client = session["client"]
        phone_code_hash = session["phone_code_hash"]
        
        await client.connect()
        await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        
        settings["is_logged"] = True
        save_settings(settings)
        
        # حفظ العميل للاستخدام لاحقاً
        clients[phone] = client
        
        return JSONResponse({"status": "ok", "message": "✅ تم تسجيل الدخول بنجاح"})
        
    except Exception as e:
        logger.error(f"خطأ في التحقق: {e}")
        if 'client' in locals():
            await client.disconnect()
        return JSONResponse({"status": "error", "message": f"❌ خطأ في التحقق: {str(e)}"})

@app.post("/send_now")
async def send_now():
    """إرسال فوري للرسالة"""
    settings = load_settings()
    
    if not settings.get("is_logged"):
        return JSONResponse({"status": "error", "message": "❌ يجب تسجيل الدخول أولاً"})
    
    phone = settings["phone"]
    api_id = int(settings["api_id"])
    api_hash = settings["api_hash"]
    groups = settings["groups"]
    message = settings["message"]
    
    if not groups:
        return JSONResponse({"status": "error", "message": "❌ يرجى إضافة مجموعات أولاً"})
    
    try:
        client = TelegramClient(f"session_{phone}", api_id, api_hash)
        await client.start(phone)
        
        sent_count = 0
        for group in groups:
            try:
                if group.startswith('https://t.me/'):
                    entity = await client.get_entity(group)
                else:
                    entity = await client.get_entity(group)
                
                await client.send_message(entity, message, link_preview=False)
                sent_count += 1
                logger.info(f"✅ أُرسل إلى {group}")
                await asyncio.sleep(2)  # انتظار بين الرسائل
                
            except Exception as e:
                logger.error(f"❌ خطأ مع {group}: {e}")
        
        await client.disconnect()
        return JSONResponse({"status": "ok", "message": f"✅ تم إرسال الرسالة إلى {sent_count} مجموعة"})
        
    except Exception as e:
        logger.error(f"خطأ في الإرسال: {e}")
        return JSONResponse({"status": "error", "message": f"❌ خطأ: {str(e)}"})

@app.post("/start_auto_send")
async def start_auto_send():
    """بدء الإرسال التلقائي"""
    settings = load_settings()
    
    if not settings.get("is_logged"):
        return JSONResponse({"status": "error", "message": "❌ يجب تسجيل الدخول أولاً"})
    
    if settings.get("is_sending"):
        return JSONResponse({"status": "error", "message": "⚠️ الإرسال التلقائي يعمل بالفعل"})
    
    settings["is_sending"] = True
    save_settings(settings)
    
    # إنشاء مهمة الإرسال التلقائي
    asyncio.create_task(auto_sender_loop())
    
    return JSONResponse({"status": "ok", "message": f"🚀 تم بدء الإرسال التلقائي كل {settings['interval']} دقيقة"})

@app.post("/stop_auto_send")
async def stop_auto_send():
    """إيقاف الإرسال التلقائي"""
    settings = load_settings()
    settings["is_sending"] = False
    save_settings(settings)
    
    return JSONResponse({"status": "ok", "message": "⏹️ تم إيقاف الإرسال التلقائي"})

@app.get("/download_files")
async def download_files():
    """تحميل جميع ملفات المشروع كملف مضغوط"""
    try:
        zip_filename = "telegram_bot_files.zip"
        
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # إضافة الملفات الرئيسية
            files_to_include = [
                "main.py",
                "get_groups.py", 
                "auto_ad.py",
                "settings.json",
                "templates/index.html",
                "pyproject.toml"
            ]
            
            for file_path in files_to_include:
                if os.path.exists(file_path):
                    zipf.write(file_path)
        
        return FileResponse(
            zip_filename,
            media_type='application/zip',
            filename=zip_filename,
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
        )
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"خطأ في التحميل: {str(e)}"})

async def auto_sender_loop():
    """حلقة الإرسال التلقائي"""
    while True:
        try:
            settings = load_settings()
            
            # إذا تم إيقاف الإرسال، توقف عن الحلقة
            if not settings.get("is_sending"):
                break
                
            if not settings.get("is_logged") or not settings.get("groups"):
                await asyncio.sleep(30)
                continue
            
            phone = settings["phone"]
            api_id = int(settings["api_id"])
            api_hash = settings["api_hash"]
            groups = settings["groups"]
            message = settings["message"]
            interval = settings["interval"]
            
            client = TelegramClient(f"session_{phone}", api_id, api_hash)
            await client.start(phone)
            
            for group in groups:
                try:
                    if group.startswith('https://t.me/'):
                        entity = await client.get_entity(group)
                    else:
                        entity = await client.get_entity(group)
                    
                    await client.send_message(entity, message, link_preview=False)
                    logger.info(f"✅ إرسال تلقائي إلى {group}")
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"❌ خطأ في الإرسال التلقائي لـ {group}: {e}")
            
            await client.disconnect()
            logger.info(f"⏳ سيتم الإرسال مرة أخرى بعد {interval} دقيقة")
            await asyncio.sleep(interval * 60)
            
        except Exception as e:
            logger.error(f"❌ خطأ في حلقة الإرسال: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5000)
