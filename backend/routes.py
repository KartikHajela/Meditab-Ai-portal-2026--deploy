from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Form,
    Response,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
import os
import secrets
from datetime import datetime
from datetime import timedelta
from starlette.responses import RedirectResponse
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
from schemas import TitleInput,SuggestionInput
import string 
# Local Imports
import models
import schemas
from db import SessionLocal
from ai_new_services import get_ai_response, transcribe_audio, generate_chat_title, analyze_document, get_text_suggestions
from utils import (
    get_db,
    is_system_message,
    sanitize_message_content,
    drive_service,
    templates,
    generate_user_hash,
    is_email_allowed,
    finalize_login,
    send_otp_email,
    send_reset_link,
    verify_access,
    verify_route_access,
    get_current_user_from_cookie,
    create_stable_hash
)

load_dotenv()
router = APIRouter()
GOOGLE_CLIENT_ID = os.getenv('gauth_client_id')
RESTRICT_SIGNUP = False

# --- SECURITY HELPER (Internal Use) ---
def verify_access(
    request: Request, allowed_roles: list, required_hash: str = None
) -> bool:
    """
    Central Security Brain:
    1. Checks if User Role is allowed.
    2. If a 'required_hash' is provided, checks if the User's Cookie Hash matches it.
    3. ALWAYS allows ADMIN.
    """
    current_role = request.cookies.get("user_role")
    current_hash = request.cookies.get("user_hash")

    if current_role == "ADMIN":
        return True

    if current_role not in allowed_roles:
        return False

    if required_hash:
        if current_hash != required_hash:
            return False 

    return True

# --- HTML ROUTES ---

@router.post("/auth/google-one-tap")
def google_one_tap_login(
    response: Response,
    login_data: schemas.GoogleOneTapInput,
    db: Session = Depends(get_db)
):
    try:
        idinfo = id_token.verify_oauth2_token(
            login_data.credential, 
            google_requests.Request(), 
            GOOGLE_CLIENT_ID
        )
        email = idinfo.get('email')
        name = idinfo.get('name')
        google_sub = idinfo.get('sub')

        if not email:
            return {"success": False, "message": "Email not found"}

        if RESTRICT_SIGNUP and not is_email_allowed(email):
             return {"success": False, "message": "Access restricted"}

        user = db.query(models.User).filter(models.User.email == email).first()

        if not user:
            user = models.User(
                email=email,
                hashed_password=secrets.token_urlsafe(32), 
                role=models.UserRole.PATIENT,
                provider_id=f"google_{google_sub}",
                is_2fa_enabled=False,
                has_signed_baa=True
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            new_profile = models.PatientProfile(
                user_id=user.id,
                full_name=name,
                lifestyle_status=models.LifestyleEnum.NONE,
                is_profile_complete=False
            )
            db.add(new_profile)
            db.commit()

        user_hash = create_stable_hash(user.email)
        
        # SET COOKIES (Including user_id for secure lookups)
        response.set_cookie(key="user_role", value=user.role.value.upper(), httponly=True)
        response.set_cookie(key="user_hash", value=user_hash, httponly=True)
        response.set_cookie(key="user_id", value=str(user.id), httponly=True) # Critical for security

        redirect_url = "/dashboard"
        if user.role == models.UserRole.PATIENT:
            redirect_url = f"/app/{user_hash}"
        elif user.role == models.UserRole.DOCTOR:
            redirect_url = f"/doctor-app/{user_hash}"

        return {
            "success": True,
            "data": {
                "token": user_hash, 
                "hash": user_hash, # Frontend needs this for local storage
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "role": user.role.value,
                    "hash": user_hash # Explicitly sending hash
                },
                "redirect_url": redirect_url
            }
        }

    except ValueError:
        return {"success": False, "message": "Invalid Token"}
    except Exception as e:
        print(f"Auth Error: {e}")
        return {"success": False, "message": "Authentication failed"}

@router.get("/", response_class=HTMLResponse)
async def serve_landing(request: Request):
    return templates.TemplateResponse("website/landing_page.html", {"request": request,"client_id": GOOGLE_CLIENT_ID})


@router.get("/access-denied", response_class=HTMLResponse)
async def access_denied(request: Request):
    return templates.TemplateResponse("website/403.html", {"request": request})

@router.get("/legal/terms", response_class=HTMLResponse)
async def serve_terms(request: Request):
    """Serves the Terms of Service page."""
    return templates.TemplateResponse("legal/terms.html", {
        "request": request,
        "current_year": datetime.now().year,
        "company_name": "Meditab Portal"
    })

@router.get("/legal/privacy-baa", response_class=HTMLResponse)
async def serve_privacy_baa(request: Request):
    """Serves the combined BAA and Privacy Policy page."""
    return templates.TemplateResponse("legal/privacy_baa.html", {
        "request": request, 
        "current_year": datetime.now().year,
        "company_name": "Meditab Portal"
    })

# --- PASSWORD RESET ROUTES ---

@router.post("/auth/forgot-password")
async def forgot_password(
    request: Request, # Need request to get base URL
    data: dict, 
    db: Session = Depends(get_db)
):
    email = data.get("email")
    user = db.query(models.User).filter(models.User.email == email).first()

    # Security: Always return "success" even if email doesn't exist (prevents user enumeration)
    if not user:
        return {"status": "success", "message": "If that email exists, a link has been sent."}

    # 1. Generate Token (UUID)
    token = secrets.token_urlsafe(32)
    
    # 2. Save to DB (15 min expiry)
    user.reset_token = token
    user.reset_token_expiry = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    # 3. Construct Link
    # Result looks like: http://127.0.0.1:8000/?action=reset_password&token=xyz...
    base_url = str(request.base_url).rstrip("/")
    reset_link = f"{base_url}/?action=reset_password&token={token}"

    # 4. Send Email
    send_reset_link(user.email, reset_link)

    return {"status": "success", "message": "Reset link sent to your email."}

@router.post("/auth/reset-password")
def reset_password_finish(data: dict, db: Session = Depends(get_db)):
    token = data.get("token")
    new_password = data.get("password")

    # 1. Find User by Token
    user = db.query(models.User).filter(models.User.reset_token == token).first()

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired link.")

    # 2. Check Expiry
    if user.reset_token_expiry and datetime.utcnow() > user.reset_token_expiry:
        raise HTTPException(status_code=400, detail="Link has expired. Please request a new one.")

    # 3. Update Password
    user.hashed_password = new_password  # Ensure you hash this if using hashing lib!
    
    # 4. Clear Token (Security: Prevent replay attacks)
    user.reset_token = None
    user.reset_token_expiry = None
    db.commit()

    return {"status": "success", "message": "Password updated successfully."}

# --- FILE UPLOAD ROUTE ---

@router.post("/upload/")
async def upload_file(
    patient_id: str = Form(...),
    session_id: str = Form(...),
    is_rec: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        p_id = int(patient_id)
    except: raise HTTPException(400, "Invalid ID")

    user_hash = create_stable_hash("temp@email.com") # Simplified for upload
    temp_filename = f"temp_{file.filename}"
    
    try:
        with open(temp_filename, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 1. DOCUMENT ANALYSIS (The "Read" Logic)
        analysis_result = None
        if file.content_type in ["application/pdf", "image/jpeg", "image/png", "image/jpg"]:
            print(f"Analyzing {file.filename}...")
            # Calls the Vision Model
            analysis_result = await analyze_document(temp_filename, file.content_type)
        
        # 2. Transcription
        transcript_text = None
        if is_rec:
            transcript_text = await transcribe_audio(temp_filename)

        # 3. Drive Upload
        drive_link = None
        drive_file_id = None
        if drive_service:
            res = drive_service.upload_to_session_folder(
                user_hash, session_id, temp_filename, file.filename
            )
            if res: 
                drive_link = res.get("link")
                drive_file_id = res.get("id")

        # 4. Save to DB (Store analysis so AI can read it later)
        # We prefer the transcript, then the analysis, then generic text
        final_transcript = transcript_text if transcript_text else analysis_result

        new_media = models.MedicalMedia(
            patient_id=p_id,
            session_id=session_id,
            file_type=file.content_type or "unknown",
            drive_file_id=drive_file_id,
            file_url=drive_link,
            transcript=final_transcript # <--- Storing AI reading here
        )
        db.add(new_media)
        db.commit()

        return {
            "status": "success",
            "file_id": drive_file_id,
            "analysis": analysis_result, # Send back to frontend
            "transcript": transcript_text
        }

    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- CHAT & VOICE ROUTES ---

@router.get("/chat_history/", response_model=List[schemas.ChatHistoryRead])
def read_chat_history(db: Session = Depends(get_db)):
    history = db.query(models.ChatHistory).all()
    for record in history:
        if record.messages:
            clean_msgs = []
            for msg in record.messages:
                if is_system_message(msg.get("content")):
                    continue
                safe_content = sanitize_message_content(msg.get("content"))
                clean_msgs.append({
                    "role": msg.get("role", "user"),
                    "content": safe_content,
                    "timestamp": msg.get("timestamp", str(datetime.utcnow())),
                })
            record.messages = clean_msgs
    return history


# --- UPDATED CHAT ROUTE ---

@router.post("/chat/send", response_model=schemas.ChatHistoryRead)
async def send_chat_message(
    chat_data: schemas.ChatInput, db: Session = Depends(get_db)
):
    # 1. Fetch User to determine Role (Doctor vs Patient)
    user = db.query(models.User).filter(models.User.id == chat_data.user_id).first()
    user_role = user.role.value.upper() if user else "PATIENT"

    # 2. Fetch or Create Chat Record
    chat_record = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.session_id == chat_data.session_id,
            models.ChatHistory.patient_id == chat_data.user_id,
        )
        .first()
    )

    # 3. Prepare History for AI
    raw_history = chat_record.messages if chat_record else []
    history_for_ai = [
        {"role": m.get("role"), "content": sanitize_message_content(m.get("content"))}
        for m in raw_history
        if not is_system_message(m.get("content"))
    ]

    # 4. Get Agentic AI Response (Passing the Role)
    try:
        ai_text = await get_ai_response(
            db_history=history_for_ai, 
            new_user_message=chat_data.message, 
            user_role=user_role
        )
    except Exception as e:
        print(f"AI Error: {e}")
        ai_text = "I'm having trouble connecting to the medical network right now."

    # 5. Construct Messages
    user_msg = {
        "role": "user",
        "content": chat_data.message,
        "timestamp": datetime.utcnow().isoformat(),
    }
    ai_msg = {
        "role": "assistant",
        "content": ai_text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # 6. Save to DB
    if chat_record:
        current_messages = list(chat_record.messages)
        current_messages.append(user_msg)
        current_messages.append(ai_msg)
        chat_record.messages = current_messages
        flag_modified(chat_record, "messages")
    else:
        chat_record = models.ChatHistory(
            patient_id=chat_data.user_id,
            session_id=chat_data.session_id,
            messages=[user_msg, ai_msg],
        )
        db.add(chat_record)

    db.commit()
    db.refresh(chat_record)
    return chat_record


# --- UPDATED VOICE ROUTE ---

@router.post("/chat/voice", response_model=schemas.ChatHistoryRead)
async def send_voice_message(
    user_id: str = Form(...),
    session_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # 0. Validate Inputs
    if str(user_id).lower() in ["undefined", "null", "none"]:
        raise HTTPException(status_code=400, detail="User ID missing.")
    
    try:
        u_id = int(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid User ID format")

    # 1. Fetch User & Role
    user = db.query(models.User).filter(models.User.id == u_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user_role = user.role.value.upper()
    user_hash = create_stable_hash(user.email)

    # 2. File Handling Setup
    file_code = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_audio_path = f"temp_audio_{file_code}.wav"
    temp_text_path = f"temp_text_{file_code}.txt"
    drive_audio_name = f"Recording_{file_code}.wav"
    drive_text_name = f"Recording_{file_code}.txt"

    try:
        # A. Save Temp Audio
        with open(temp_audio_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # B. Transcribe (Using New Whisper-Large-V3)
        transcribed_text = await transcribe_audio(temp_audio_path)
        if not transcribed_text or "Error" in transcribed_text:
            transcribed_text = "(Audio unintelligible)"

        # C. Save Transcript Temp
        with open(temp_text_path, "w", encoding="utf-8") as f:
            f.write(transcribed_text)

        # D. Upload to Google Drive (If Service Active)
        audio_drive_id = None
        audio_drive_link = None

        if drive_service:
            # Upload Audio
            audio_res = drive_service.upload_to_session_folder(
                user_email=user_hash,
                session_id=session_id,
                file_path=temp_audio_path,
                file_name=drive_audio_name,
            )
            if audio_res:
                audio_drive_id = audio_res.get("id")
                audio_drive_link = audio_res.get("link")

            # Upload Transcript Text
            drive_service.upload_to_session_folder(
                user_email=user_hash,
                session_id=session_id,
                file_path=temp_text_path,
                file_name=drive_text_name,
            )

        # E. Save Media Record to DB
        audio_db_record = models.MedicalMedia(
            patient_id=u_id,
            session_id=session_id,
            file_type="audio/wav",
            drive_file_id=audio_drive_id,
            file_url=audio_drive_link,
            transcript=transcribed_text,
        )
        db.add(audio_db_record)
        db.commit()

    finally:
        # Cleanup Temp Files
        if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
        if os.path.exists(temp_text_path): os.remove(temp_text_path)

    # 3. Chat Logic
    chat_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == session_id,
        models.ChatHistory.patient_id == u_id,
    ).first()

    raw_history = chat_record.messages if chat_record and chat_record.messages else []
    
    history_for_ai = [
        {"role": m.get("role"), "content": sanitize_message_content(m.get("content"))}
        for m in raw_history
        if not is_system_message(m.get("content"))
    ]

    # 4. Get Agentic AI Response (Passing Role)
    try:
        ai_text = await get_ai_response(
            db_history=history_for_ai, 
            new_user_message=transcribed_text,
            user_role=user_role
        )
    except Exception as e:
        print(f"AI Voice Error: {e}")
        ai_text = "I'm having trouble connecting to the AI service."

    user_msg = {
        "role": "user",
        "content": transcribed_text,
        "timestamp": datetime.utcnow().isoformat(),
        "type": "audio_transcript",
    }
    ai_msg = {
        "role": "assistant",
        "content": ai_text,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if chat_record:
        current_msgs = list(chat_record.messages) if chat_record.messages else []
        current_msgs.append(user_msg)
        current_msgs.append(ai_msg)
        chat_record.messages = current_msgs
        flag_modified(chat_record, "messages")
    else:
        chat_record = models.ChatHistory(
            patient_id=u_id, session_id=session_id, messages=[user_msg, ai_msg]
        )
        db.add(chat_record)

    db.commit()
    db.refresh(chat_record)
    return chat_record


@router.post("/chat/generate_title")
async def generate_title_route(data: TitleInput):
    """Generates a smart 3-5 word title for the chat."""
    title = await generate_chat_title(data.message)
    return {"title": title}

@router.post("/chat/autocomplete")
async def autocomplete_endpoint(data: SuggestionInput):
    """Provides dynamic text suggestions."""
    suggestions = await get_text_suggestions(data.text)
    return {"suggestions": suggestions}

# --- USER & PROFILE ENDPOINTS ---

@router.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    final_role = models.UserRole.PATIENT
    final_provider_id = None

    if user.role == models.UserRole.DOCTOR:
        if not user.provider_id:
            raise HTTPException(status_code=400, detail="Provider ID is required.")
        pid = user.provider_id.strip()
        if pid.startswith("88"):
            final_role = models.UserRole.DOCTOR
        elif pid.startswith("00"):
            final_role = models.UserRole.ADMIN
        else:
            raise HTTPException(status_code=400, detail="Invalid Provider ID.")
        final_provider_id = pid

    new_user = models.User(
        email=user.email,
        hashed_password=user.password,
        role=final_role,
        provider_id=final_provider_id,
        has_signed_baa=user.has_signed_baa,
        is_2fa_enabled=user.is_2fa_enabled,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # UPDATED: Create PatientProfile
    new_profile = models.PatientProfile(
        user_id=new_user.id,
        full_name=user.email.split("@")[0],
        lifestyle_status=models.LifestyleEnum.NONE,
        is_profile_complete=False
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_user)
    return new_user

@router.post("/login")
def login(
    response: Response,
    user_credentials: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    
    if not user or user_credentials.password != user.hashed_password:
        raise HTTPException(status_code=403, detail="Invalid Credentials")

    # 2FA Logic...
    if user.is_2fa_enabled:
        otp = "".join(secrets.choice(string.digits) for _ in range(6))
        user.otp_code = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)
        db.commit()
        send_otp_email(user.email, otp)
        return {
            "status": "2fa_required",
            "user_id": user.id,
            "message": f"Verification code sent to {user.email}"
        }

    # Standard Login
    user_hash = create_stable_hash(user.email)
    
    # Set Secure Cookies
    response.set_cookie(key="user_role", value=user.role.value.upper(), httponly=True)
    response.set_cookie(key="user_hash", value=user_hash, httponly=True)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)

    redirect_url = "/dashboard"
    if user.role == models.UserRole.PATIENT:
        redirect_url = f"/app/{user_hash}"
    elif user.role == models.UserRole.DOCTOR:
        redirect_url = f"/doctor-app/{user_hash}"
    elif user.role == models.UserRole.ADMIN:
        redirect_url = "/admin"

    return {
        "status": "success",
        "id": user.id,
        "role": user.role,
        "email": user.email,
        "hash": user_hash, # Send hash for frontend
        "redirect_url": redirect_url,
    }

# --- NEW ROUTE: VERIFY OTP ---
@router.post("/auth/verify-2fa")
def verify_2fa_login(
    response: Response,
    data: schemas.VerifyOTPInput,
    db: Session = Depends(get_db)
):
    user = db.query(models.User).filter(models.User.id == data.user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Validate OTP
    if not user.otp_code or user.otp_code != data.otp_code:
        raise HTTPException(status_code=400, detail="Invalid OTP code")

    # 2. Validate Expiry
    if user.otp_expiry and datetime.utcnow() > user.otp_expiry:
        raise HTTPException(status_code=400, detail="OTP code expired")

    # 3. Clear OTP after success
    user.otp_code = None
    user.otp_expiry = None
    db.commit()

    # 4. Finalize Login
    return finalize_login(user, response)

@router.get("/app/{user_hash}", response_class=HTMLResponse)
async def serve_user_app(user_hash: str, request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user = get_current_user_from_cookie(request, db)
    
    # 2. Verify URL Hash matches User
    # if not user or not verify_route_access(user, user_hash):
    #     return RedirectResponse("/access-denied")
    
    if not user:
        print("DEBUG: Access Denied - No User Found in Cookie")
        return RedirectResponse("/access-denied")
        
    if not verify_route_access(user, user_hash):
        print(f"DEBUG: Access Denied - Hash Mismatch for {user.email}")
        return RedirectResponse("/access-denied")
        
    return templates.TemplateResponse("website/home.html", {"request": request})

@router.get("/app/{user_hash}/profile", response_class=HTMLResponse)
async def serve_profile_page(user_hash: str, request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user = get_current_user_from_cookie(request, db)
    if not user or not verify_route_access(user, user_hash):
        return RedirectResponse("/access-denied")

    # 2. Fetch Profiles
    profile = db.query(models.PatientProfile).filter(models.PatientProfile.user_id == user.id).first()
    doctor_profile = None
    
    if user.role == models.UserRole.DOCTOR:
        doctor_profile = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == user.id).first()
        if not doctor_profile:
            doctor_profile = models.DoctorProfile(user_id=user.id)
            db.add(doctor_profile)
            db.commit()

    return templates.TemplateResponse("website/profiles.html", {
        "request": request,
        "user_id": user.id,
        "user_role": user.role.value.upper(),
        "user_hash": user_hash,
        "profile": profile,
        "doctor_profile": doctor_profile,
        "specialties": models.MedicalSpecialty
    })

@router.post("/app/{user_hash}/profile/update")
async def update_profile(user_hash: str, data: dict, request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user = get_current_user_from_cookie(request, db)
    if not user or not verify_route_access(user, user_hash):
        raise HTTPException(status_code=403, detail="Unauthorized Access")

    # 2. Update Patient Profile
    profile = db.query(models.PatientProfile).filter(models.PatientProfile.user_id == user.id).first()
    if profile:
        profile.full_name = data.get('full_name', profile.full_name)
        profile.phone = data.get('phone', profile.phone)
        if data.get('date_of_birth'):
            try:
                profile.date_of_birth = datetime.strptime(data['date_of_birth'], '%Y-%m-%d').date()
            except ValueError:
                pass # Handle invalid date format gracefully
        profile.gender = data.get('gender', profile.gender)
        profile.address = data.get('address', profile.address)
        
        # Medical Fields
        profile.blood_group = data.get('blood_group', profile.blood_group)
        profile.height_cm = float(data['height']) if data.get('height') else profile.height_cm
        profile.weight_kg = float(data['weight']) if data.get('weight') else profile.weight_kg
        profile.allergies = data.get('allergies', profile.allergies)
        profile.chronic_conditions = data.get('conditions', profile.chronic_conditions)
        profile.current_medications = data.get('medications', profile.current_medications)
        profile.emergency_name = data.get('emergency_name', profile.emergency_name)
        profile.emergency_relation = data.get('emergency_relation', profile.emergency_relation)
        profile.emergency_phone = data.get('emergency_phone', profile.emergency_phone)
        profile.lifestyle_status = data.get('lifestyle_status', profile.lifestyle_status)
        profile.occupation = data.get('occupation', profile.occupation)
        profile.insurance_provider = data.get('insurance_details', profile.insurance_provider)

    # 3. Update Doctor Profile (if applicable)
    if user.role == models.UserRole.DOCTOR:
        doc = db.query(models.DoctorProfile).filter(models.DoctorProfile.user_id == user.id).first()
        if doc:
            doc.bio = data.get('bio', doc.bio)
            if 'specialty' in data: doc.specialty = data['specialty']
            if 'is_available' in data: doc.is_available = data['is_available']

    db.commit()
    return {"status": "updated"}

# 3. Check Completion Status
@router.get("/app/{user_hash}/profile/status")
async def check_profile_status(user_hash: str, request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user = get_current_user_from_cookie(request, db)
    if not user or not verify_route_access(user, user_hash):
        return {"percent": 0} 

    # 2. Calculate Status
    filled_fields = 0
    total_fields = 0
    
    p = user.patient_profile
    if p:
        fields = [p.full_name, p.phone, p.date_of_birth, p.gender, p.address, p.blood_group, p.allergies]
        total_fields += 7
        filled_fields += sum(1 for f in fields if f)

    percent = int((filled_fields / total_fields) * 100) if total_fields > 0 else 0
    return {"percent": percent}

@router.get("/medical_media/", response_model=List[schemas.MediaRead])
def read_medical_media(db: Session = Depends(get_db)):
    return db.query(models.MedicalMedia).all()


# --- DOCTOR & DRIVE ROUTES (Unchanged Logic, just DB Names) ---

@router.get("/doctor-app/{user_hash}", response_class=HTMLResponse)
async def serve_doctor_dashboard(user_hash: str, request: Request):
    if not verify_access(request, allowed_roles=["DOCTOR"], required_hash=user_hash):
        return RedirectResponse("/access-denied")

    db = SessionLocal()
    try:
        stats = {
            "total_users": db.query(models.User).count(),
            "total_chats": db.query(models.ChatHistory).count(),
            "total_files": db.query(models.MedicalMedia).count(),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        return templates.TemplateResponse(
            "doctor/base.html",
            {"request": request, "stats": stats, "user_hash": user_hash},
        )
    finally:
        db.close()

@router.get("/doctor-app/{user_hash}/files", response_class=HTMLResponse)
async def serve_doctor_files(user_hash: str, request: Request):
    if not verify_access(request, allowed_roles=["DOCTOR"], required_hash=user_hash):
        return RedirectResponse("/access-denied")

    drive_files = []
    if drive_service:
        try:
            drive_files = (
                drive_service.service.files()
                .list(
                    pageSize=20,
                    fields="nextPageToken, files(id, name, mimeType, webViewLink, createdTime)",
                )
                .execute()
                .get("files", [])
            )
        except Exception as e:
            print(f"Error fetching from Drive: {e}")

    return templates.TemplateResponse(
        "admin/doctor_files.html",
        {"request": request, "files": drive_files, "user_hash": user_hash},
    )

@router.get("/app/{user_hash}/files-api")
def list_user_files(user_hash: str, request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user = get_current_user_from_cookie(request, db)
    if not user or not verify_route_access(user, user_hash):
        return [] 
    
    if not drive_service: return []
    
    # 2. Use the hash to get files (assuming your Drive logic stores folders by hash)
    raw_files = drive_service.get_all_files_for_user(user_hash)
    
    cleaned_files = []
    for f in raw_files:
        # Filter out temp transcripts/recordings from the UI list if desired
        if f['name'].endswith('.txt') and 'Recording_' in f['name']:
            continue
            
        cleaned_files.append({
            "id": f['id'],
            "name": f['name'],
            "mimeType": f['mimeType'],
            "webViewLink": f['webViewLink'],
            "iconLink": f.get('iconLink'),
            "createdTime": f.get('createdTime')
        })
        
    cleaned_files.sort(key=lambda x: x['createdTime'], reverse=True)
    return cleaned_files

@router.delete("/files/{drive_file_id}")
def delete_file_drive(drive_file_id: str, db: Session = Depends(get_db)):
    if drive_service:
        drive_service.delete_file(drive_file_id)

    db_record = db.query(models.MedicalMedia).filter(models.MedicalMedia.drive_file_id == drive_file_id).first()
    if db_record:
        db.delete(db_record)
        db.commit()
        
    return {"status": "deleted", "id": drive_file_id}

@router.get("/doctor-app/{user_hash}/chats", response_class=HTMLResponse)
async def serve_doctor_chats(user_hash: str, request: Request):
    if not verify_access(request, allowed_roles=["DOCTOR"], required_hash=user_hash):
        return RedirectResponse("/access-denied")

    db = SessionLocal()
    try:
        chats = (
            db.query(models.ChatHistory).order_by(models.ChatHistory.id.desc()).all()
        )
        return templates.TemplateResponse(
            "admin/doctor_chats.html",
            {"request": request, "chats": chats, "user_hash": user_hash},
        )
    finally:
        db.close()

