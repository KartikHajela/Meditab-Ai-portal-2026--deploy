from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Enum, DateTime, Text, JSON, Float, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db import Base
import enum
from datetime import datetime

# ==========================================
# 1. ENUMS
# ==========================================

class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"

class GenderEnum(str, enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"

class BloodGroupEnum(str, enum.Enum):
    A_POS = "A+"
    A_NEG = "A-"
    B_POS = "B+"
    B_NEG = "B-"
    O_POS = "O+"
    O_NEG = "O-"
    AB_POS = "AB+"
    AB_NEG = "AB-"

class LifestyleEnum(str, enum.Enum):
    NONE = "None"
    SOCIAL = "Social"
    MODERATE = "Moderate"
    HEAVY = "Heavy"

class MedicalSpecialty(str, enum.Enum):
    GENERAL = "General Physician"
    CARDIOLOGY = "Cardiologist"
    GYNECOLOGY = "Gynecologist"
    DERMATOLOGY = "Dermatologist"
    ORTHOPEDICS = "Orthopedist"
    NEUROLOGY = "Neurologist"
    PEDIATRICS = "Pediatrician"

class CaseStatus(str, enum.Enum):
    TRIAGE = "Triage"
    PENDING = "Pending"
    ASSIGNED = "Assigned"
    EMERGENCY = "Emergency"
    CLOSED = "Closed"

class SeverityEnum(str, enum.Enum):
    MILD = "Mild"
    MODERATE = "Moderate"
    CRITICAL = "Critical"

# ==========================================
# 2. CORE USER & AUTH
# ==========================================

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.PATIENT)
    
    # Auth & Security
    provider_id = Column(String, nullable=True) 
    has_signed_baa = Column(Boolean, default=False)
    is_2fa_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # --- NEW COLUMNS FOR 2FA ---
    otp_code = Column(String, nullable=True)
    otp_expiry = Column(DateTime, nullable=True)

    # --- NEW COLUMNS FOR PASSWORD RESET ---
    reset_token = Column(String, nullable=True)
    reset_token_expiry = Column(DateTime, nullable=True)

    # Relationships
    patient_profile = relationship("PatientProfile", back_populates="user", uselist=False)
    doctor_profile = relationship("DoctorProfile", back_populates="user", uselist=False)
    
    medical_media = relationship("MedicalMedia", back_populates="patient")
    chat_history = relationship("ChatHistory", back_populates="patient")
    
    # NOTE: 'cases' relationship logic is tricky because User can be Patient OR Doctor.
    # We define cases here specifically as "cases where this user is the PATIENT".
    cases = relationship("MedicalCase", back_populates="patient", foreign_keys="MedicalCase.patient_id")

# ==========================================
# 3. PROFILES
# ==========================================

class PatientProfile(Base):
    __tablename__ = "patient_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    # Identity
    full_name = Column(String, index=True)
    profile_picture_url = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(Enum(GenderEnum), nullable=True)
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    
    # Emergency
    emergency_name = Column(String, nullable=True)
    emergency_relation = Column(String, nullable=True)
    emergency_phone = Column(String, nullable=True)

    # Clinical Baseline
    blood_group = Column(Enum(BloodGroupEnum), nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    current_medications = Column(Text, nullable=True)
    surgical_history = Column(Text, nullable=True)
    family_medical_history = Column(Text, nullable=True)

    # Lifestyle
    lifestyle_status = Column(Enum(LifestyleEnum), default=LifestyleEnum.NONE)
    occupation = Column(String, nullable=True)
    insurance_provider = Column(String, nullable=True)
    insurance_policy_no = Column(String, nullable=True)

    is_profile_complete = Column(Boolean, default=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="patient_profile")
    sessions = relationship("MedicalSession", back_populates="patient_profile")

    @property
    def bmi(self):
        if self.height_cm and self.weight_kg:
            height_m = self.height_cm / 100
            return round(self.weight_kg / (height_m * height_m), 2)
        return None


class DoctorProfile(Base):
    __tablename__ = "doctor_profiles"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    
    specialty = Column(Enum(MedicalSpecialty), default=MedicalSpecialty.GENERAL)
    is_available = Column(Boolean, default=True)
    active_cases = Column(Integer, default=0)
    bio = Column(Text, nullable=True)
    
    user = relationship("User", back_populates="doctor_profile")
    # This relationship matches the "doctor" relationship in MedicalCase
    assigned_cases = relationship("MedicalCase", back_populates="doctor")

# ==========================================
# 4. MEDICAL RECORDS
# ==========================================

class MedicalSession(Base):
    __tablename__ = "medical_sessions"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(Integer, ForeignKey("patient_profiles.id"))
    session_uuid = Column(String, index=True)
    
    chief_complaint = Column(Text, nullable=True)
    symptom_onset = Column(String, nullable=True)
    severity = Column(Enum(SeverityEnum), default=SeverityEnum.MILD)
    
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    sp_o2 = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    patient_profile = relationship("PatientProfile", back_populates="sessions")


class MedicalCase(Base):
    __tablename__ = "medical_cases"
    
    id = Column(Integer, primary_key=True)
    
    # 1. Patient Link (Points to User)
    patient_id = Column(Integer, ForeignKey("users.id"))
    
    # 2. Doctor Link (FIXED: Points to DoctorProfile, NOT User)
    # This fixes the NoForeignKeysError
    doctor_id = Column(Integer, ForeignKey("doctor_profiles.id"), nullable=True)
    
    chat_history_id = Column(Integer, ForeignKey("chat_history.id"), nullable=True)
    
    status = Column(Enum(CaseStatus), default=CaseStatus.TRIAGE)
    priority_score = Column(Integer, default=0)
    ai_summary = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # Relationships
    patient = relationship("User", foreign_keys=[patient_id], back_populates="cases")
    doctor = relationship("DoctorProfile", back_populates="assigned_cases")


class ChatHistory(Base):
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String, index=True, unique=True)
    messages = Column(JSON) 
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("User", back_populates="chat_history")


class MedicalMedia(Base):
    __tablename__ = "medical_media"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String)
    
    file_type = Column(String)
    drive_file_id = Column(String, nullable=True)
    file_url = Column(String, nullable=True)
    transcript = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("User", back_populates="medical_media")