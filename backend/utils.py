import os
from fastapi import Request,HTTPException, Response
from fastapi.templating import Jinja2Templates 
from starlette.responses import RedirectResponse 
from db import SessionLocal
from sqladmin.authentication import AuthenticationBackend
from drive_service import DriveAPI
import hashlib
import models
import smtplib
import ssl
from email.message import EmailMessage
from sqlalchemy.orm import Session
import string


# --- 1. CENTRALIZED PATHS ---
base_dir = os.path.dirname(os.path.realpath(__file__))
frontend_dir = os.path.join(base_dir, "..", "frontend")
templates_dir = os.path.join(frontend_dir, "templates")
static_dir = os.path.join(frontend_dir, "static")


# --- 2. SHARED SERVICES ---
# Initialize Templates (So routes.py can use it)
templates = Jinja2Templates(directory=templates_dir)

# Initialize Drive (So routes.py and views.py can use it)
try:
    drive_service = DriveAPI()
    print("Google Drive Service Initialized")
except Exception as e:
    print(f"Warning: Drive Service failed: {e}")
    drive_service = None


# --- 3. HELPERS ---
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def is_system_message(content): return False 

def sanitize_message_content(content): return str(content) if content else ""

def generate_user_hash(email: str) -> str:
    """
    Creates a consistent 15-char hash from an email.
    Example: 'kartik@gmail.com' -> '7a9b2c3d4e5f6g7'
    """
    salt = "your_super_secret_project_salt_v1"  # Change this to a random string!
    raw_string = f"{email}{salt}"
    # Generate SHA256 hash and take first 15 chars
    return hashlib.sha256(raw_string.encode()).hexdigest()[:15]

# --- STABLE HASH FUNCTION (Fixes Redirect Loop) ---
def create_stable_hash(email: str) -> str:
    """
    Creates a deterministic hash based on email.
    This ensures the hash generated at Login matches the hash checked at Verification.
    """
    salt = "mediconnect_secure_salt_2026" # Constant salt ensures stability
    raw = f"{email}{salt}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()[:16] # Return first 16 chars


async def check_admin_access(request: Request, call_next):
    # Middleware logic moved here to keep main.py clean
    if request.url.path.startswith("/admin"):
        role = request.cookies.get("user_role")
        if role in ["PATIENT", "DOCTOR"]:
            return RedirectResponse(url="/access-denied") 
        
    elif request.url.path.startswith("/portal/doctor"):
        role = request.cookies.get("user_role")
        if role in ["PATIENT"]:
            return RedirectResponse(url="/access-denied")
            
    return await call_next(request)

def is_email_allowed(email: str) -> bool:
    # Example logic: Allow only specific domains or check a DB list
    allowed_domains = ["gmail.com", "outlook.com"] 
    return True # Default to True for now

def finalize_login(user, response: Response):
    """
    Sets cookies and determines redirect URL.
    Used by both standard login and 2FA verification.
    """
    user_hash = create_stable_hash(user.email)

    # Set Secure Cookies
    response.set_cookie(key="user_role", value=user.role.value.upper(), httponly=True)
    response.set_cookie(key="user_hash", value=user_hash, httponly=True)

    # Determine Redirect
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
        "redirect_url": redirect_url,
    }

def send_otp_email(receiver_email: str, otp: str):
    sender = "test2codee@gmail.com"
    app_password = "snbl dnrk jwgv tman" # Provided credentials

    msg = EmailMessage()
    msg['Subject'] = 'Verification Code - Meditab'
    msg['From'] = sender
    msg['To'] = receiver_email
    
    # Text Fallback
    msg.set_content(f"Your OTP is {otp}. It expires in 5 minutes.")

    # HTML Version
    html_version = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="padding: 20px; border: 1px solid #ddd; border-radius: 10px; max-width: 400px; margin: 0 auto;">
                <h2 style="color: #0e7490; text-align: center;">Meditab Portal</h2>
                <p style="text-align: center; color: #334155;">Use the secure code below to sign in:</p>
                <h1 style="background: #f1f5f9; padding: 15px; text-align: center; letter-spacing: 8px; border-radius: 8px; color: #0f172a;">{otp}</h1>
                <p style="font-size: 12px; color: gray; text-align: center; margin-top: 20px;">This code expires in 5 minutes.</p>
            </div>
        </body>
    </html>
    """
    msg.add_alternative(html_version, subtype='html')

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(sender, app_password)
            server.send_message(msg)
        print(f"✅ OTP sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"❌ Email Error: {e}")
        return False

def send_reset_link(receiver_email: str, link: str):
    sender = "test2codee@gmail.com"
    app_password = "snbl dnrk jwgv tman" 

    msg = EmailMessage()
    msg['Subject'] = 'Reset Your Password - Meditab'
    msg['From'] = sender
    msg['To'] = receiver_email
    
    msg.set_content(f"Click here to reset your password: {link}")

    html_version = f"""
    <html>
        <body style="font-family: 'Inter', sans-serif; background-color: #f8fafc; padding: 20px;">
            <div style="max-width: 450px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border: 1px solid #e2e8f0;">
                <h2 style="color: #0e7490; text-align: center; margin-top: 0;">Password Reset</h2>
                <p style="color: #64748b; text-align: center;">You requested to reset your password. Click the button below to create a new one.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{link}" style="background-color: #0e7490; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">Reset Password</a>
                </div>
                <p style="font-size: 12px; color: #94a3b8; text-align: center;">If you didn't ask for this, you can safely ignore this email.<br>Link expires in 15 minutes.</p>
            </div>
        </body>
    </html>
    """
    msg.add_alternative(html_version, subtype='html')

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls(context=context)
            server.login(sender, app_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email Error: {e}")
        return False

# --- HELPER: Secure User Retrieval ---
def get_current_user_from_cookie(request: Request, db: Session) -> models.User:
    """
    Retrieves the logged-in user via the secure 'user_id' cookie.
    This prevents users from simply changing the URL hash to access others' data.
    """
    uid_str = request.cookies.get("user_id")
    if not uid_str:
        print(f"DEBUG: Missing user_id cookie. Cookies found: {request.cookies.keys()}")
        return None
    try:
        user = db.query(models.User).filter(models.User.id == int(uid_str)).first()
        return user
    except:
        print(f"DEBUG: Error fetching user: {e}")
        return None

def verify_route_access(user: models.User, url_hash: str) -> bool:
    """
    Ensures the user accessing the URL owns the hash in the URL.
    """
    if not user: 
        return False
    # Verify the URL hash matches the user's generated hash
    expected_hash = create_stable_hash(user.email)
    if expected_hash != url_hash:
        print(f"DEBUG: Hash Mismatch! Expected: {expected_hash}, Got: {url_hash}")
        return False
    
    return True

# --- SECURITY HELPER (Legacy Internal Use) ---
def verify_access(
    request: Request, allowed_roles: list, required_hash: str = None
) -> bool:
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

# --- 4. ADMIN SECURITY ---
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        return True

    async def logout(self, request: Request) -> bool:
        return True

    async def authenticate(self, request: Request) -> bool:
        # Check for the cookie set by our login endpoint
        role = request.cookies.get("user_role")
        if role in ["ADMIN"]: return True
        elif role in ["PATIENT","DOCTOR"]: raise HTTPException(status_code=302, headers={"Location": "/access-denied"})
        return False
    
