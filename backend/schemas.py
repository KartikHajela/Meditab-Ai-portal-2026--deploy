from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import models  # Importing Enums from your models.py

# --- GOOGLE LOGIN ---
class GoogleOneTapInput(BaseModel):
    credential: str

# ==========================================
# 1. PATIENT PROFILE SCHEMAS
# ==========================================

class PatientProfileBase(BaseModel):
    # Identity
    full_name: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[models.GenderEnum] = None
    address: Optional[str] = None
    
    # Emergency
    emergency_name: Optional[str] = None
    emergency_relation: Optional[str] = None
    emergency_phone: Optional[str] = None

    # Clinical Baseline
    blood_group: Optional[models.BloodGroupEnum] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    surgical_history: Optional[str] = None
    family_medical_history: Optional[str] = None

    # Lifestyle
    lifestyle_status: Optional[models.LifestyleEnum] = models.LifestyleEnum.NONE
    occupation: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_policy_no: Optional[str] = None

class PatientProfileRead(PatientProfileBase):
    id: int
    user_id: int
    is_profile_complete: bool
    bmi: Optional[float] = None # Calculated property

    class Config:
        from_attributes = True

# ==========================================
# 2. DOCTOR PROFILE SCHEMAS
# ==========================================

class DoctorProfileBase(BaseModel):
    specialty: models.MedicalSpecialty = models.MedicalSpecialty.GENERAL
    is_available: bool = True
    bio: Optional[str] = None

class DoctorProfileRead(DoctorProfileBase):
    id: int
    user_id: int
    active_cases: int

    class Config:
        from_attributes = True

# ==========================================
# 3. USER SCHEMAS
# ==========================================

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = "default_password" 
    role: models.UserRole = models.UserRole.PATIENT
    has_signed_baa: bool = False
    is_2fa_enabled: bool = False
    provider_id: Optional[str] = None # Required if Role is Doctor

class UserRead(BaseModel):
    id: int
    email: str
    role: models.UserRole
    provider_id: Optional[str] = None
    has_signed_baa: bool
    is_2fa_enabled: bool
    
    # Return the appropriate profile
    patient_profile: Optional[PatientProfileRead] = None 
    doctor_profile: Optional[DoctorProfileRead] = None

    class Config:
        from_attributes = True

# ==========================================
# 4. CHAT & MEDIA SCHEMAS
# ==========================================

class MediaRead(BaseModel):
    id: int
    file_type: str
    drive_file_id: Optional[str] = None
    file_url: Optional[str] = None
    transcript: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ChatHistoryRead(BaseModel):
    session_id: str
    messages: List[Dict[str, Any]] 

    class Config:
        from_attributes = True

class ChatInput(BaseModel):
    user_id: int
    session_id: str
    message: str
    role: str = "user"

class TitleInput(BaseModel):
    message: str

class SuggestionInput(BaseModel):
    text: str

class VerifyOTPInput(BaseModel):
    user_id: int
    otp_code: str