from fastapi import FastAPI, Depends, HTTPException, Request, status, UploadFile, File, Form, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified
from typing import List
import os
import shutil
import asyncio
from datetime import datetime
from starlette.responses import RedirectResponse 

# FastAPI Admin Imports
from sqladmin import Admin, ModelView, BaseView, expose
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy import func

# Local Imports
import models
import schemas
from db import SessionLocal, engine
from ai_services import get_ai_response, transcribe_audio 
from drive_service import DriveAPI

# --- INITIALIZATION ---
models.Base.metadata.create_all(bind=engine)

# --- PATH CONFIGURATION ---
base_dir = os.path.dirname(os.path.realpath(__file__))
frontend_dir = os.path.join(base_dir, "..", "frontend")

try:
    drive_service = DriveAPI()
    print("Google Drive Service Initialized")
except Exception as e:
    print(f"Warning: Drive Service failed: {e}")
    drive_service = None

app = FastAPI()

if os.path.exists(os.path.join(frontend_dir, "static")):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(frontend_dir, "templates"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def block_patient_from_admin(request: Request, call_next):
    # 1. Check if user is trying to access any /admin route
    if request.url.path.startswith("/admin"):
        # 2. Check role from cookie
        role = request.cookies.get("user_role")
        
        # 3. If Patient, FORCE redirect to your custom 403 page
        if role in ["PATIENT","DOCTOR"]:
            return RedirectResponse(url="/access-denied")
    
    elif request.url.path.startswith("/dashboard"):
        # 2. Check role from cookie
        role = request.cookies.get("user_role")
        
        # 3. If Patient, FORCE redirect to your custom 403 page
        if role in ["DOCTOR"]:
            return RedirectResponse(url="/access-denied")
            
    # Otherwise, let the request proceed (to AdminAuth or other routes)
    return await call_next(request)

# --- 1. DEFINE ADMIN SECURITY ---
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        return True

    async def logout(self, request: Request) -> bool:
        return True

    async def authenticate(self, request: Request) -> bool:
        # Check for the cookie set by our login endpoint
        role = request.cookies.get("user_role")
        
        # 1. If Doctor or Admin, Allow Access
        if role in ["ADMIN"]:
            return True
        
        # 2. If Patient, FORCE Redirect to 403 Page
        if role == "PATIENT":
            raise HTTPException(status_code=302, headers={"Location": "/access-denied"})

        elif role == "DOCTOR":
            raise HTTPException(status_code=302, headers={"Location": "/access-denied"})
               
        # 3. If Not Logged In, return False (Redirects to Admin Login)
        return False

# Initialize Auth Backend
authentication_backend = AdminAuth(secret_key="super_secret_key")

# Initialize Admin
admin = Admin(app, engine, templates_dir=os.path.join(frontend_dir, "templates"), authentication_backend=authentication_backend)

# --- ADMIN VIEWS ---
class UserAdmin(ModelView, model=models.User):
    column_list = [models.User.id, models.User.email, models.User.role, models.User.provider_id]
    column_searchable_list = [models.User.email, models.User.provider_id]
    icon = "fa-solid fa-user"
    category = "User Management"

class ProfileAdmin(ModelView, model=models.Profile):
    column_list = [models.Profile.id, models.Profile.full_name, models.Profile.current_status]
    icon = "fa-solid fa-address-card"
    category = "User Management"

class MediaAdmin(ModelView, model=models.MedicalMedia):
    column_list = [models.MedicalMedia.id, models.MedicalMedia.patient_id, models.MedicalMedia.file_type]
    icon = "fa-solid fa-file-medical"
    category = "Clinical Data"

class ChatAdmin(ModelView, model=models.ChatHistory):
    column_list = [models.ChatHistory.id, models.ChatHistory.session_id]
    icon = "fa-solid fa-comments"
    category = "Clinical Data"

class AnalyticsView(BaseView):
    name = "Analytics Dashboard"
    icon = "fa-solid fa-chart-pie"

    # 1. Main Dashboard
    @expose("/analytics", methods=["GET"])
    async def analytics_page(self, request: Request):
        db = SessionLocal()
        try:
            stats = {
                "total_users": db.query(models.User).count(),
                "total_chats": db.query(models.ChatHistory).count(),
                "db_record_count": db.query(models.MedicalMedia).count(),
                "drive_status": "Active" if drive_service else "Disconnected",
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return await self.templates.TemplateResponse(
                request=request, name="admin/admin_analytics.html", context={"request": request, "stats": stats}
            )
        finally:
            db.close()

    # 2. Live Files from Google Drive
    @expose("/analytics/files", methods=["GET"])
    async def files_page(self, request: Request):
        drive_files = []
        if drive_service:
            try:
                drive_files = drive_service.service.files().list(
                    pageSize=20, 
                    fields="nextPageToken, files(id, name, mimeType, webViewLink, createdTime)"
                ).execute().get('files', [])
            except Exception as e:
                print(f"Error fetching from Drive: {e}")

        return await self.templates.TemplateResponse(
            request=request, name="admin/admin_files.html", context={"files": drive_files}
        )

    # 3. Chat Analytics
    @expose("/analytics/chats", methods=["GET"])
    async def chats_page(self, request: Request):
        db = SessionLocal()
        try:
            chats = db.query(models.ChatHistory).order_by(models.ChatHistory.id.desc()).all()
            return await self.templates.TemplateResponse(
                request=request, name="admin/admin_chats.html", context={"chats": chats}
            )
        finally:
            db.close()

admin.add_view(UserAdmin)
admin.add_view(ProfileAdmin)
admin.add_view(MediaAdmin)
admin.add_view(ChatAdmin)
admin.add_view(AnalyticsView)

# --- HELPERS ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def is_system_message(content): return False 
def sanitize_message_content(content): return str(content) if content else ""

# --- HTML ROUTES ---

@app.get('/', response_class=HTMLResponse)
async def serve_landing(request: Request):
    return templates.TemplateResponse("website/landing_page.html", {"request": request})

@app.get('/dashboard', response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("website/home.html", {"request": request})

# 1. Doctor Dashboard Route (Changed from /admin/doctor to /portal/doctor)
@app.get('/portal/doctor', response_class=HTMLResponse)
async def serve_doctor_admin(request: Request):
    role = request.cookies.get("user_role")
    # Strict Check: Only Doctors or Admins allowed
    if role not in ["DOCTOR", "ADMIN"]: 
        return RedirectResponse("/access-denied")
    
    # FETCH STATS & PASS TO TEMPLATE
    db = SessionLocal()
    try:
        stats = {
            "total_users": db.query(models.User).count(),
            "total_chats": db.query(models.ChatHistory).count(),
            "db_record_count": db.query(models.MedicalMedia).count(),
            "drive_status": "Active" if drive_service else "Disconnected",
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        return templates.TemplateResponse("admin/doctor_analytics.html", {"request": request, "stats": stats})
    finally:
        db.close()

# # 2. Super Admin Route (Changed from /admin/superAdmin to /portal/superAdmin)
# @app.get('/portal/superAdmin', response_class=HTMLResponse)
# async def serve_super_admin(request: Request):
#     role = request.cookies.get("user_role")
#     # Strict Check: Only ADMIN allowed
#     if role != "ADMIN": 
#         return RedirectResponse("/access-denied")
    
#     # FETCH STATS & PASS TO TEMPLATE
#     db = SessionLocal()
#     try:
#         stats = {
#             "total_users": db.query(models.User).count(),
#             "total_chats": db.query(models.ChatHistory).count(),
#             "db_record_count": db.query(models.MedicalMedia).count(),
#             "drive_status": "Active" if drive_service else "Disconnected",
#             "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#         }
#         return templates.TemplateResponse("admin/admin_analytics.html", {"request": request, "stats": stats})
#     finally:
#         db.close()

@app.get("/access-denied", response_class=HTMLResponse)
async def access_denied(request: Request):
    return templates.TemplateResponse("website/403.html", {"request": request})

# --- FILE UPLOAD ROUTE ---

@app.post("/upload/")
async def upload_file(
    patient_id: int = Form(...), session_id: str = Form(...), is_rec: bool = Form(False),
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    MAX_SIZE = 30 * 1024 * 1024 
    file.file.seek(0, 2); file_size = file.file.tell(); file.file.seek(0)
    if file_size > MAX_SIZE: raise HTTPException(status_code=413, detail="File too large")

    user = db.query(models.User).filter(models.User.id == patient_id).first()
    if not user: raise HTTPException(status_code=404, detail=f"User ID {patient_id} not found")
    
    temp_filename = f"temp_{file.filename}"
    try:
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        transcript_text = None
        if is_rec:
            try:
                transcript_text = await transcribe_audio(temp_filename)
                if not transcript_text or "Error" in transcript_text: transcript_text = "(Audio unintelligible)"
            except Exception as e:
                print(f"Transcription failed: {e}")
                transcript_text = "(Transcription Failed)"

        drive_file_id = None
        drive_link = None
        
        if drive_service:
            result = drive_service.upload_to_session_folder(
                user_email=user.email, session_id=session_id, file_path=temp_filename, file_name=file.filename
            )
            if result:
                drive_file_id = result.get('id')
                drive_link = result.get('link')
        
        new_media = models.MedicalMedia(
            patient_id=patient_id, session_id=session_id, file_type=file.content_type or "unknown",
            drive_file_id=drive_file_id, file_url=drive_link, transcript=transcript_text
        )
        db.add(new_media); db.commit(); db.refresh(new_media)

        return { "status": "success", "file_id": drive_file_id, "file_url": drive_link, "user_verified": user.email }
            
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)

# --- CHAT & VOICE ROUTES ---

@app.get("/chat_history/", response_model=List[schemas.ChatHistoryRead])
def read_chat_history(db: Session = Depends(get_db)):
    history = db.query(models.ChatHistory).all()
    for record in history:
        if record.messages:
            clean_msgs = []
            for msg in record.messages:
                if is_system_message(msg.get('content')): continue
                safe_content = sanitize_message_content(msg.get('content'))
                clean_msgs.append({
                    "role": msg.get("role", "user"),
                    "content": safe_content,
                    "timestamp": msg.get("timestamp", str(datetime.utcnow()))
                })
            record.messages = clean_msgs
    return history

@app.post("/chat/send", response_model=schemas.ChatHistoryRead)
async def send_chat_message(chat_data: schemas.ChatInput, db: Session = Depends(get_db)):
    chat_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == chat_data.session_id, models.ChatHistory.patient_id == chat_data.user_id
    ).first()

    raw_history = chat_record.messages if chat_record else []
    history_for_ai = [
        {"role": m.get("role"), "content": sanitize_message_content(m.get("content"))}
        for m in raw_history if not is_system_message(m.get('content'))
    ]

    try: ai_text = await get_ai_response(history_for_ai, chat_data.message)
    except Exception as e: ai_text = "I'm having trouble connecting to the AI service."

    user_msg = {"role": "user", "content": chat_data.message, "timestamp": datetime.utcnow().isoformat()}
    ai_msg = {"role": "assistant", "content": ai_text, "timestamp": datetime.utcnow().isoformat()}

    if chat_record:
        current_messages = list(chat_record.messages)
        current_messages.append(user_msg); current_messages.append(ai_msg)
        chat_record.messages = current_messages
        flag_modified(chat_record, "messages") 
    else:
        chat_record = models.ChatHistory(
            patient_id=chat_data.user_id, session_id=chat_data.session_id, messages=[user_msg, ai_msg]
        )
        db.add(chat_record)

    db.commit(); db.refresh(chat_record)
    
    if chat_record.messages:
        chat_record.messages = [
            {**m, "content": sanitize_message_content(m["content"])} 
            for m in chat_record.messages if not is_system_message(m.get('content'))
        ]
    return chat_record

@app.post("/chat/voice", response_model=schemas.ChatHistoryRead)
async def send_voice_message(
    user_id: int = Form(...), session_id: str = Form(...),
    file: UploadFile = File(...), db: Session = Depends(get_db)
):
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_filename = f"voice_{session_id}_{timestamp_str}.wav"
    drive_filename = f"Voice_Note_{timestamp_str}.wav"
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")

    try:
        with open(temp_filename, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        
        drive_id = None; drive_url = None
        if drive_service:
            result = drive_service.upload_to_session_folder(
                user_email=user.email, session_id=session_id, file_path=temp_filename, file_name=drive_filename
            )
            if result: drive_id = result.get('id'); drive_url = result.get('link')

        audio_db_record = models.MedicalMedia(
            patient_id=user_id, session_id=session_id, file_type="audio/wav",
            drive_file_id=drive_id, file_url=drive_url, transcript="(Processing...)" 
        )
        db.add(audio_db_record); db.commit(); db.refresh(audio_db_record)
        
        transcribed_text = await transcribe_audio(temp_filename)
        if not transcribed_text or "Error" in transcribed_text: transcribed_text = "(Audio unintelligible)"
            
        audio_db_record.transcript = transcribed_text
        db.add(audio_db_record); db.commit() 
            
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)

    chat_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == session_id, models.ChatHistory.patient_id == user_id
    ).first()

    raw_history = chat_record.messages if chat_record else []
    history_for_ai = [
        {"role": m.get("role"), "content": sanitize_message_content(m.get("content"))}
        for m in raw_history if not is_system_message(m.get('content'))
    ]

    try: ai_text = await get_ai_response(history_for_ai, transcribed_text)
    except: ai_text = "I'm having trouble connecting to the AI service."

    user_msg = {"role": "user", "content": transcribed_text, "timestamp": datetime.utcnow().isoformat(), "type": "audio_transcript"}
    ai_msg = {"role": "assistant", "content": ai_text, "timestamp": datetime.utcnow().isoformat()}

    if chat_record:
        msgs = list(chat_record.messages)
        msgs.append(user_msg); msgs.append(ai_msg)
        chat_record.messages = msgs
        flag_modified(chat_record, "messages")
    else:
        chat_record = models.ChatHistory(
            patient_id=user_id, session_id=session_id, messages=[user_msg, ai_msg]
        )
        db.add(chat_record)

    db.commit(); db.refresh(chat_record)
    
    if chat_record.messages:
        chat_record.messages = [
            {**m, "content": sanitize_message_content(m["content"])} 
            for m in chat_record.messages if not is_system_message(m.get('content'))
        ]
    return chat_record

# --- USER & PROFILE ENDPOINTS ---

@app.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # ROLE LOGIC
    final_role = models.UserRole.PATIENT
    final_provider_id = None

    if user.role == models.UserRole.DOCTOR:
        if not user.provider_id: raise HTTPException(status_code=400, detail="Provider ID is required.")
        pid = user.provider_id.strip()
        if pid.startswith("88"): final_role = models.UserRole.DOCTOR
        elif pid.startswith("00"): final_role = models.UserRole.ADMIN
        else: raise HTTPException(status_code=400, detail="Invalid Provider ID. Must start with '88' or '00'.")
        final_provider_id = pid
    
    new_user = models.User(
        email=user.email, hashed_password=user.password, role=final_role, 
        provider_id=final_provider_id, has_signed_baa=user.has_signed_baa, is_2fa_enabled=user.is_2fa_enabled
    )
    db.add(new_user); db.commit(); db.refresh(new_user)

    new_profile = models.Profile(
        user_id=new_user.id, full_name=user.email.split("@")[0], current_status=models.MedicalStatus.MILD
    )
    db.add(new_profile); db.commit(); db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.UserRead)
def login(response: Response, user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user or user_credentials.password != user.hashed_password:
        raise HTTPException(status_code=403, detail="Invalid Credentials")
    
    # Set Cookie
    response.set_cookie(key="user_role", value=user.role.value.upper(), httponly=True)
    return user

@app.post("/users/{user_id}/profile", response_model=schemas.ProfileRead)
def create_profile_for_user(user_id: int, profile: schemas.ProfileCreate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user: raise HTTPException(status_code=404, detail="User not found")
    if user.profile: raise HTTPException(status_code=400, detail="User already has a profile")

    new_profile = models.Profile(**profile.dict(), user_id=user_id)
    db.add(new_profile); db.commit(); db.refresh(new_profile)
    return new_profile

@app.get("/medical_media/", response_model=List[schemas.MediaRead])
def read_medical_media(db: Session = Depends(get_db)):
    return db.query(models.MedicalMedia).all()