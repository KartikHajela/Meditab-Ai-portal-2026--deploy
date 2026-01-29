from fastapi import Request
from datetime import datetime

# FastAPI Admin Imports
from sqladmin import ModelView, BaseView, expose

# Local Imports
import models
from db import SessionLocal
from utils import drive_service

# --- ADMIN VIEWS ---

class UserAdmin(ModelView, model=models.User):
    column_list = [
        models.User.id, 
        models.User.email, 
        models.User.role, 
        models.User.provider_id,
        models.User.created_at
    ]
    column_searchable_list = [models.User.email, models.User.provider_id]
    icon = "fa-solid fa-user"
    category = "User Management"

# UPDATED: Renamed from ProfileAdmin to PatientProfileAdmin
class PatientProfileAdmin(ModelView, model=models.PatientProfile):
    column_list = [
        models.PatientProfile.id, 
        models.PatientProfile.full_name, 
        models.PatientProfile.gender,
        models.PatientProfile.blood_group,
        models.PatientProfile.is_profile_complete
    ]
    column_searchable_list = [models.PatientProfile.full_name, models.PatientProfile.phone]
    icon = "fa-solid fa-hospital-user"
    category = "User Management"
    name = "Patient Profile"
    name_plural = "Patient Profiles"

# NEW: Doctor Profile View
class DoctorProfileAdmin(ModelView, model=models.DoctorProfile):
    column_list = [
        models.DoctorProfile.id, 
        models.DoctorProfile.specialty, 
        models.DoctorProfile.is_available,
        models.DoctorProfile.active_cases
    ]
    icon = "fa-solid fa-user-doctor"
    category = "User Management"
    name = "Doctor Profile"
    name_plural = "Doctor Profiles"

# NEW: Medical Session View (The "Dynamic" Data)
class MedicalSessionAdmin(ModelView, model=models.MedicalSession):
    column_list = [
        models.MedicalSession.id, 
        models.MedicalSession.session_uuid, 
        models.MedicalSession.severity, 
        models.MedicalSession.created_at
    ]
    icon = "fa-solid fa-notes-medical"
    category = "Clinical Data"
    name = "Medical Session"

# NEW: Medical Case View (Workflow)
class MedicalCaseAdmin(ModelView, model=models.MedicalCase):
    column_list = [
        models.MedicalCase.id, 
        models.MedicalCase.status, 
        models.MedicalCase.priority_score, 
        models.MedicalCase.created_at
    ]
    icon = "fa-solid fa-briefcase-medical"
    category = "Clinical Data"
    name = "Medical Case"

class MediaAdmin(ModelView, model=models.MedicalMedia):
    column_list = [
        models.MedicalMedia.id, 
        models.MedicalMedia.patient_id, 
        models.MedicalMedia.file_type,
        models.MedicalMedia.created_at
    ]
    icon = "fa-solid fa-file-medical"
    category = "Clinical Data"

class ChatAdmin(ModelView, model=models.ChatHistory):
    column_list = [
        models.ChatHistory.id, 
        models.ChatHistory.session_id, 
        models.ChatHistory.created_at
    ]
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
                "total_sessions": db.query(models.MedicalSession).count(), # Added new metric
                "total_cases": db.query(models.MedicalCase).count(),       # Added new metric
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