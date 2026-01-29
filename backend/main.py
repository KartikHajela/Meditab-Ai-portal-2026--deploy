from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

# FastAPI Admin Imports
from sqladmin import Admin

# Local Imports
import models
from db import engine
from ai_services import get_ai_response, transcribe_audio 
from utils import templates_dir, static_dir, AdminAuth, check_admin_access, static_dir
from views import (
    UserAdmin, 
    PatientProfileAdmin, 
    DoctorProfileAdmin,   # New
    MedicalSessionAdmin,  # New
    MedicalCaseAdmin,     # New
    MediaAdmin, 
    ChatAdmin, 
    AnalyticsView
)

from routes import router

 
# --- INITIALIZATION ---
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Middleware (Imported from utils)
app.middleware("http")(check_admin_access)

# --- ROUTER REGISTRATION ---
app.include_router(router)

# --- ADMIN PANEL SETUP ---
authentication_backend = AdminAuth(secret_key="super_secret_key")
admin = Admin(app, engine, templates_dir=templates_dir, authentication_backend=authentication_backend)

# 1. User Management
admin.add_view(UserAdmin)
admin.add_view(PatientProfileAdmin)
admin.add_view(DoctorProfileAdmin)

# 2. Clinical Data & Workflow
admin.add_view(MedicalSessionAdmin)
admin.add_view(MedicalCaseAdmin)
admin.add_view(MediaAdmin)
admin.add_view(ChatAdmin)

# 3. Analytics
admin.add_view(AnalyticsView)