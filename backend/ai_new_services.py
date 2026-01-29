import os
import json
import time
import base64
import re
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# --- THIRD PARTY LIBS ---
import pypdf 
from groq import AsyncGroq
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# --- OCR ENGINE (PaddleOCR) ---
try:
    from paddleocr import PaddleOCR
    # Initialize OCR Engine once (Global) to save RAM
    ocr_engine = PaddleOCR(
        use_angle_cls=True,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        lang='en',
        show_log=False 
    )
    OCR_AVAILABLE = True
except ImportError:
    print("⚠️ PaddleOCR not found. OCR features will be disabled.")
    OCR_AVAILABLE = False
except Exception as e:
    print(f"⚠️ PaddleOCR Init Failed: {e}")
    OCR_AVAILABLE = False

# --- PDF GENERATION ---
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

load_dotenv()

# --- CONFIGURATION & CLIENTS ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY") or os.getenv("gauth_api_key")
if not GROQ_API_KEY:
    raise ValueError("❌ Missing GROQ_API_KEY in .env file")

# 1. Main Chat Client (Reasoning - 70B for best logic)
llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.3-70b-versatile",
    temperature=0.3
)

# 2. Fast Client (Autocomplete - 8B for speed)
fast_llm = ChatGroq(
    groq_api_key=GROQ_API_KEY,
    model_name="llama-3.1-8b-instant",
    temperature=0.1
)

# 3. Vision & Audio Client
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

REPORTS_DIR = "static/reports"
os.makedirs(REPORTS_DIR, exist_ok=True)


# ==========================================
# 1. VISION & DOCUMENT ANALYSIS ENGINE
# ==========================================

def run_paddle_ocr(file_path: str) -> str:
    """Helper: Runs PaddleOCR on a file."""
    if not OCR_AVAILABLE: return "[System: OCR Module not installed]"
    try:
        result = ocr_engine.ocr(file_path, cls=True)
        extracted_text = []
        if result and result[0]:
            for line in result:
                if line:
                    for word_info in line:
                        extracted_text.append(word_info[1][0])
        full_text = "\n".join(extracted_text)
        return full_text if full_text.strip() else "[OCR: No readable text found]"
    except Exception as e:
        return f"[OCR Error: {str(e)}]"

async def analyze_document(file_path: str, mime_type: str) -> str:
    """Reads PDFs (Text+OCR) and Images (Vision+OCR)."""
    try:
        analysis_context = ""
        # A. Handle PDF
        if "pdf" in mime_type:
            raw_text = ""
            try:
                with open(file_path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        text = page.extract_text()
                        if text: raw_text += text + "\n"
            except Exception: pass
            
            if len(raw_text.strip()) < 50: # Scanned PDF Check
                ocr_text = run_paddle_ocr(file_path)
                analysis_context = f"[SYSTEM: Scanned PDF Content (via OCR)]:\n{ocr_text[:6000]}"
            else:
                analysis_context = f"[SYSTEM: PDF Content]:\n{raw_text[:6000]}"

        # B. Handle Images
        elif "image" in mime_type:
            ocr_text = run_paddle_ocr(file_path)
            with open(file_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            
            vision_response = await groq_client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Analyze this medical image. Identify scan type, findings, and abnormalities."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded_string}"}},
                    ],
                }],
                temperature=0.1, max_tokens=500
            )
            analysis_context = (f"[SYSTEM: Visual Analysis]: {vision_response.choices[0].message.content}\n\n"
                                f"[SYSTEM: OCR Text]: {ocr_text}")
        else:
            analysis_context = f"[SYSTEM: User uploaded file of type {mime_type}]"

        return analysis_context
    except Exception as e:
        return f"[SYSTEM: Analysis Error: {str(e)}]"


# ==========================================
# 2. AUTOCOMPLETE ENGINE (FIXED)
# ==========================================

async def get_text_suggestions(current_input: str) -> List[str]:
    """
    Studio-Grade Predictive Text Engine.
    Uses Regex-based extraction to ensure stability even if the LLM 'yaps'.
    """
    # 1. Validation: Don't autocomplete on empty/nonsense input
    if not current_input or len(current_input.strip()) < 2: 
        return []

    # 2. Strict Prompting
    prompt = f"""
    Role: Keyboard Autocomplete Engine.
    Task: Complete the user's sentence logically.
    Input: "{current_input}"
    
    Constraints:
    - Return a JSON List of 3 strings.
    - NO polite talk. NO conversational filler.
    - The suggestions must strictly continue the input text.
    
    Example:
    Input: "I feel d" -> Output: ["dizzy", "drained", "down lately"]
    """

    try:
        # 3. Execution
        res = await fast_llm.ainvoke([HumanMessage(content=prompt)])
        raw_content = res.content.strip()

        # 4. Bulletproof Parsing (Regex)
        # Finds anything that looks like ["..."] inside the response
        match = re.search(r'\[.*\]', raw_content, re.DOTALL)
        if match:
            json_str = match.group(0)
            suggestions = json.loads(json_str)
            # Extra safety: ensure it's a list of strings
            return [str(s) for s in suggestions if isinstance(s, str)][:3]
        
        return []

    except Exception as e:
        # Fail silently for autocomplete (don't break UI)
        return []


async def generate_smart_replies(chat_history: list) -> List[str]:
    """
    Studio-Grade Contextual Suggestions.
    Dynamically generates reply buttons based on what the AI just asked.
    """
    defaults = ["Upload Report", "Book Appointment", "Emergency"]
    
    # 1. Validation: Need history to be smart
    if not chat_history or len(chat_history) == 0:
        return defaults

    # 2. Context Extraction: Get the last thing the AI said
    last_msg = None
    for msg in reversed(chat_history):
        if msg.get('role') == 'assistant':
            last_msg = msg.get('content')
            break
            
    if not last_msg: return defaults

    # 3. Dynamic Prompting
    prompt = f"""
    Role: UX Writing Assistant.
    Context: The AI Doctor just said: "{last_msg[:300]}..."
    
    Task: Generate 3 short, relevant 'Quick Reply' buttons for the patient.
    Rules:
    - Max 3-4 words per button.
    - Must directly answer the Doctor's question/statement.
    - Return strictly JSON list.
    
    Example:
    Doctor: "How long have you had the fever?"
    Output: ["Since yesterday", "2 days", "A week"]
    """

    try:
        res = await fast_llm.ainvoke([HumanMessage(content=prompt)])
        
        # 4. Regex Parsing (Same robustness logic)
        match = re.search(r'\[.*\]', res.content.strip(), re.DOTALL)
        if match:
            options = json.loads(match.group(0))
            return [str(o)[:20] for o in options][:3] # Truncate long buttons
            
        return defaults

    except Exception:
        return defaults

# ==========================================
# 3. PDF GENERATOR ENGINE ("JANE DOE" REPLICA)
# ==========================================

# ==========================================
# 3. PDF GENERATOR ENGINE (HEIDI/JANE DOE REPLICA)
# ==========================================

class MedicalReportGenerator:
    @staticmethod
    def create_pdf(filename: str, data: dict):
        file_path = os.path.join(REPORTS_DIR, filename)
        doc = SimpleDocTemplate(file_path, pagesize=A4, 
                                rightMargin=40, leftMargin=40, 
                                topMargin=40, bottomMargin=40)
        
        # --- 1. STYLES & METRICS ---
        styles = getSampleStyleSheet()
        
        # Colors (Matched to Reference)
        TEAL_COLOR = colors.HexColor('#008B96') # The specific "Heidi" Teal
        TEXT_COLOR = colors.HexColor('#1f2937')
        GRAY_LABEL = colors.HexColor('#6b7280')
        LIGHT_BG = colors.HexColor('#f9fafb')
        BORDER_COLOR = colors.HexColor('#e5e7eb')

        # Custom Paragraph Styles
        s_brand = ParagraphStyle('Brand', parent=styles['Heading1'], fontSize=22, textColor=TEAL_COLOR, fontName='Helvetica-Bold')
        s_contact = ParagraphStyle('Contact', parent=styles['Normal'], fontSize=8, textColor=GRAY_LABEL, alignment=TA_RIGHT, leading=10)
        
        s_title = ParagraphStyle('DocTitle', parent=styles['Heading2'], fontSize=16, textColor=TEXT_COLOR, fontName='Helvetica-Bold', spaceBefore=15, spaceAfter=20)
        
        s_section = ParagraphStyle('Section', parent=styles['Heading3'], fontSize=11, textColor=TEAL_COLOR, fontName='Helvetica-Bold', spaceBefore=15, spaceAfter=8)
        
        s_label = ParagraphStyle('Label', parent=styles['Normal'], fontSize=7, textColor=GRAY_LABEL, fontName='Helvetica', leading=8)
        s_value = ParagraphStyle('Value', parent=styles['Normal'], fontSize=9, textColor=TEXT_COLOR, fontName='Helvetica', leading=11)
        s_value_bold = ParagraphStyle('ValueBold', parent=s_value, fontName='Helvetica-Bold')
        
        s_body = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9, textColor=TEXT_COLOR, leading=13)

        story = []
        width, height = A4
        available_width = width - 80

        # --- 2. HEADER SECTION ---
        # Logo Left | Contact Right
        header_tbl_data = [
            [Paragraph("MEDITAB", s_brand), 
             Paragraph("meditab.ai<br/>support@meditab.ai", s_contact)]
        ]
        t_header = Table(header_tbl_data, colWidths=[available_width * 0.7, available_width * 0.3])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ]))
        story.append(t_header)
        story.append(Spacer(1, 20))
        
        story.append(Paragraph("Medical Report Template", s_title))

        # --- 3. ADMINISTRATIVE DETAILS (Grid Layout) ---
        story.append(Paragraph("Administrative Details", s_section))
        
        req_date = datetime.now().strftime("%d/%m/%Y")
        
        # We use a wrapper table to create the "Form Field" look (Label above Value)
        def field(label, value, bold=False):
            style = s_value_bold if bold else s_value
            return [Paragraph(label, s_label), Paragraph(value, style)]

        # Row 1
        row1 = [
            field("Patient Name:", data.get('patient_name', 'Unknown'), bold=True),
            field("Age/ DOB:", data.get('age', 'Unknown') ),
            field("Sex/Gender:", data.get('gender', 'Not Specified'))
        ]
        # Row 2
        row2 = [
            field("Claim Number:", "A987654321"),
            field("Request Date:", req_date),
            field("Received From:", "MEDITAB AI PORTAL")
        ]

        # Helper to build the visual row
        def build_row_table(row_data):
            # Inner tables for each cell to stack Label/Value vertically
            cells = []
            for item in row_data:
                cells.append(Table([[item[0]], [item[1]]], style=[
                    ('LEFTPADDING', (0,0), (-1,-1), 0),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 1),
                    ('TOPPADDING', (0,1), (-1,1), 1),
                ]))
            return cells

        admin_data = [
            build_row_table(row1),
            build_row_table(row2)
        ]
        
        t_admin = Table(admin_data, colWidths=[available_width/3]*3)
        t_admin.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,0), 0.5, BORDER_COLOR), # Line after Row 1
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(t_admin)
        story.append(Spacer(1, 15))

        # --- 4. GP CREDENTIALS ---
        story.append(Paragraph("General Practitioner Credentials", s_section))
        
        # Using a layout that mimics the "Form" look
        cred_data = [
            [Paragraph("Practice Name:", s_label), Paragraph("MEDITAB VIRTUAL CLINIC", s_value)],
            [Paragraph("GP Name:", s_label), Paragraph("DR. AI ASSISTANT", s_value)],
            [Paragraph("GP Credentials:", s_label), Paragraph("MD, FRACGP (AI Verified)", s_value)]
        ]
        t_cred = Table(cred_data, colWidths=[80, available_width-80])
        t_cred.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (0,-1), 0),
        ]))
        story.append(t_cred)
        
        story.append(Spacer(1, 8))
        disclaimer = "This report has been prepared by Dr. AI Assistant based on the consultation session provided. I have been treating the patient for the duration of this session."
        story.append(Paragraph(disclaimer, s_body))
        story.append(Spacer(1, 15))

        # --- 5. SUBJECTIVE FINDINGS ---
        story.append(Paragraph("Subjective Findings", s_section))
        
        # Sub-sections
        story.append(Paragraph("Presenting Complaint", s_label))
        story.append(Paragraph(data.get("chief_complaint", "N/A"), s_body))
        story.append(Spacer(1, 8))
        
        story.append(Paragraph("History & Context", s_label))
        story.append(Paragraph(data.get("history", "N/A"), s_body))
        story.append(Spacer(1, 8))
        
        story.append(Paragraph("Impact on Lifestyle (Functional Limitations)", s_label))
        story.append(Paragraph(data.get("lifestyle_impact", "Not reported."), s_body))
        story.append(Spacer(1, 20))

        # --- 6. OBJECTIVE FINDINGS (THE BOX TABLE) ---
        story.append(Paragraph("Objective Findings", s_section))
        
        # Columns: Diagnosis | Medications
        # We need a proper grid here with headers
        
        obj_header = [Paragraph("Clinical Assessment / Diagnosis", s_label), Paragraph("Management Plan (Rx)", s_label)]
        
        meds_text = "<br/>".join([f"• {m}" for m in data['medications']]) if data.get('medications') else "No medications prescribed."
        
        obj_row = [
            Paragraph(data.get("diagnosis", "Pending Review"), s_body),
            Paragraph(meds_text, s_body)
        ]
        
        t_obj = Table([obj_header, obj_row], colWidths=[available_width * 0.5, available_width * 0.5])
        t_obj.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, BORDER_COLOR),
            ('BACKGROUND', (0,0), (-1,0), LIGHT_BG), # Header Background
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t_obj)
        story.append(Spacer(1, 20))

        # --- 7. PROGNOSIS & OPINION ---
        story.append(Paragraph("Prognosis and Medical Opinion", s_section))
        
        story.append(Paragraph("Prognosis", s_label))
        story.append(Paragraph(data.get('prognosis', 'Condition requires monitoring.'), s_body))
        story.append(Spacer(1, 8))
        
        story.append(Paragraph("Medical Opinion / Response to Requested Questions", s_label))
        story.append(Paragraph(data.get('medical_opinion', 'Patient is advised to rest.'), s_body))
        story.append(Spacer(1, 8))
        
        story.append(Paragraph("Recommendations", s_label))
        story.append(Paragraph(data.get('recommendations', 'Follow up as required.'), s_body))
        story.append(Spacer(1, 30))

        # --- 8. CERTIFICATION & SIGNATURE ---
        story.append(Paragraph("Certification and Signature", s_section))
        story.append(Paragraph("I confirm that the information in the above report is generated based on the provided clinical session.", s_body))
        story.append(Spacer(1, 15))

        # Signature Box
        sig_headers = [Paragraph("GP Name and Signature:", s_label), Paragraph("Date Completed:", s_label)]
        sig_values = [Paragraph("Dr. AI Assistant", s_value_bold), Paragraph(req_date, s_value)]
        
        # Stack them
        sig_data = [
            [Table([[sig_headers[0]], [sig_values[0]]], style=[('LEFTPADDING',(0,0),(-1,-1),0)]),
             Table([[sig_headers[1]], [sig_values[1]]], style=[('LEFTPADDING',(0,0),(-1,-1),0)])]
        ]
        
        t_sig = Table(sig_data, colWidths=[available_width * 0.6, available_width * 0.4])
        t_sig.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 1, TEXT_COLOR), # The Signature Line
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t_sig)
        
        # --- FOOTER ---
        story.append(Spacer(1, 30))
        story.append(Paragraph("meditab.ai  |  support@meditab.ai", s_contact))
        story.append(Spacer(1, 5))
        note = "Note: This document is AI-generated by Meditab Portal. Verify with primary clinical records."
        story.append(Paragraph(note, ParagraphStyle('Note', parent=s_label, alignment=TA_CENTER)))

        doc.build(story)
        return file_path

@tool
def generate_hospital_pdf(
    patient_name: str, 
    age: str,
    gender: str,
    chief_complaint: str, 
    history: str, 
    lifestyle_impact: str, 
    diagnosis: str, 
    medications: str, 
    prognosis: str, 
    medical_opinion: str, 
    recommendations: str
):
    """
    Generates a formal PDF medical report.
    CRITICAL: Do NOT call this unless you know the Patient's Name, Age, and Gender.
    """
    # --- LOCK 2: CODE-LEVEL VALIDATION ---
    # If the LLM tries to sneak in "Unknown" data, we reject it here.
    missing_fields = []
    
    if not patient_name or patient_name.lower() in ["unknown", "user", "patient", "n/a"]:
        missing_fields.append("Patient Name")
    if not age or age.lower() in ["unknown", "0", "n/a"]:
        missing_fields.append("Age")
    if not gender or gender.lower() in ["unknown", "not specified", "n/a"]:
        missing_fields.append("Gender")
        
    if missing_fields:
        # This return string is seen by the AI, forcing it to ask the user.
        return f"SYSTEM_REJECTION: You cannot generate a report yet. You are missing: {', '.join(missing_fields)}. Ask the user for these details first."

    try:
        # 1. Filename Hygiene
        safe_name = "".join(x for x in patient_name if x.isalnum())[:10]
        filename = f"Report_{safe_name}_{int(time.time())}.pdf"
        
        # 2. Parse Medications
        med_list = [m.strip().title() for m in medications.replace('\n', ',').split(',') if m.strip()] if medications else ["None reported"]

        # 3. Data Structure (Now includes Age/Gender)
        data = {
            "patient_name": patient_name.title(),
            "age": age,
            "gender": gender.title(),
            "chief_complaint": chief_complaint,
            "history": history,
            "lifestyle_impact": lifestyle_impact,
            "diagnosis": diagnosis,
            "medications": med_list,
            "prognosis": prognosis,
            "medical_opinion": medical_opinion,
            "recommendations": recommendations
        }
        
        # 4. Generate
        path = MedicalReportGenerator.create_pdf(filename, data)
        return f"REPORT_GENERATED_AT: /static/reports/{filename}"

    except Exception as e:
        return f"SYSTEM ERROR: Report generation failed. Reason: {str(e)}"

# Bind the tool to the LLM (Must be done after function definition)
model_with_tools = llm.bind_tools([generate_hospital_pdf])


# ==========================================
# 4. MAIN CHAT LOGIC (RE-ACT AGENT)
# ==========================================

async def get_ai_response(db_history: list, new_user_message: str, user_role: str = "PATIENT", file_context: str = None) -> str:
    """
    Studio-Grade Orchestrator with Strict Data Validation.
    """
    
    # 1. GATEKEEPER SYSTEM PROMPT
    base_instructions = """
    You are Meditab, an empathetic AI Health Assistant.
    
    **PROTOCOL 1: LANGUAGE MIRRORING**
    - Respond in the EXACT language/script of the user (Hindi, Gujarati, English).
    
    **PROTOCOL 2: THE "NO-GHOST" RULE (Report Generation)**
    - User Request: "Make a report" / "Report banao".
    - **CRITICAL CHECK**: Do you have the **PATIENT IDENTITY**?
      1. **Name** (NOT "User" or "Unknown")
      2. **Age** 3. **Gender**
    - **ACTION**: If ANY of these are missing, you MUST REFUSE to generate the report.
      - *Say:* "I need to know who this report is for. What is the patient's name, age, and gender?"
    
    **PROTOCOL 3: CLINICAL DATA CHECK**
    - Once Identity is confirmed, check for **CLINICAL VITALS**:
      1. Chief Complaint (Symptoms)
      2. Duration (How long?)
      3. Severity/History
    - **ACTION**: If missing, ask for them specifically.
    
    **PROTOCOL 4: DOCTOR SIMULATION**
    - When calling 'generate_hospital_pdf', fill 'Prognosis' and 'Opinion' by INFERRING from symptoms. 
    - NEVER leave fields blank.
    """
    
    messages = [SystemMessage(content=base_instructions)]
    
    if file_context:
        messages.append(SystemMessage(content=f"SYSTEM NOTICE: User file analysis:\n{file_context}"))

    for msg in db_history:
        role = HumanMessage if msg['role'] == 'user' else AIMessage
        messages.append(role(content=str(msg['content'])))
    
    messages.append(HumanMessage(content=new_user_message))

    # --- AGENT LOOP ---
    try:
        response = await model_with_tools.ainvoke(messages)
        
        if response.tool_calls:
            # Add the "intent" to history
            messages.append(response) 
            
            for tool_call in response.tool_calls:
                if tool_call['name'] == 'generate_hospital_pdf':
                    try:
                        # Execute Tool (which now has the Validation Layer)
                        tool_result = generate_hospital_pdf.invoke(tool_call['args'])
                    except Exception as e:
                        tool_result = f"Error: {str(e)}"
                    
                    # Feed result (or Rejection Message) back to LLM
                    messages.append(ToolMessage(
                        tool_call_id=tool_call['id'],
                        name=tool_call['name'],
                        content=tool_result
                    ))
            
            # Final Response: LLM explains the result (or asks for the missing name)
            final_response = await model_with_tools.ainvoke(messages)
            return final_response.content
        
        return response.content

    except Exception as e:
        print(f"AI Agent Error: {e}")
        return "System is currently busy. Please try again."

# ==========================================
# 5. UTILITIES
# ==========================================

async def transcribe_audio(file_path: str) -> str:
    """
    Studio-grade transcription using Groq Whisper Large V3.
    Features:
    - Auto-language detection (Hindi/English/Gujarati support).
    - Medical context prompting for higher accuracy.
    - Robust file validation and error logging.
    """
    # 1. Validation: Ensure file exists before calling expensive API
    if not file_path or not os.path.exists(file_path):
        print(f"❌ [Audio Error]: File not found at {file_path}")
        return "(Error: Audio file missing)"

    try:
        # 2. "Priming" the Model: This prompt guides Whisper to expect medical terms
        # and mixed languages, significantly improving accuracy for Hinglish/Gujarati.
        medical_context = "Medical consultation, symptoms, diagnosis, patient history, hindi, gujarati, english mixed."

        with open(file_path, "rb") as file:
            # 3. Execution
            transcription = await groq_client.audio.transcriptions.create(
                file=(os.path.basename(file_path), file.read()), # Pass filename for better format detection
                model="whisper-large-v3",
                prompt=medical_context,  # <--- KEY UPGRADE
                response_format="json",
                # language="en",         # REMOVED: Enabled auto-detection for Indic languages
                temperature=0.0          # Deterministic output (less hallucinations)
            )
        
        # 4. output Cleaning
        text = transcription.text.strip()
        
        if not text:
            return "(No speech detected in audio)"
            
        return text

    except Exception as e:
        # 5. Observability: Log actual error for dev, return safe string for UI
        print(f"⚠️ [Transcription Failed]: {str(e)}")
        return "(Audio processing temporarily unavailable)"

async def generate_chat_title(message_content: str) -> str:
    """
    Generates a professional, concise (3-5 words) clinical title for the chat session.
    Uses robust cleaning to ensure the title is UI-ready.
    """
    # 1. Fast Validation: Don't waste API calls on empty/short strings
    if not message_content or len(message_content.strip()) < 2: 
        return "New Consultation"

    # 2. Input Prep: Clean formatting to save tokens and reduce confusion
    clean_content = message_content[:250].replace("\n", " ").strip()

    # 3. "Studio-Grade" Prompting
    # We strictly enforce format to prevent conversational replies.
    prompt = f"""
    Role: Medical Admin.
    Task: Generate a 3-5 word professional title for this patient query.
    Input: "{clean_content}"
    
    Constraints:
    - Use clinical terminology where possible (e.g., "Stomach hurt" -> "Abdominal Pain").
    - Do NOT use quotes, periods, or prefixes like "Title:".
    - Return ONLY the text.
    """

    try:
        # 4. Execution
        res = await fast_llm.ainvoke([HumanMessage(content=prompt)])
        raw_title = res.content.strip()

        # 5. Robust Sanitization Pipeline
        # Removes "Title:", quotes, extra spaces, and trailing dots
        clean_title = raw_title.replace('"', '').replace("'", "").strip().rstrip(".")
        
        # Handle cases where LLM might say "Title: The Title"
        if clean_title.lower().startswith("title:"):
            clean_title = clean_title[6:].strip()

        # Final Fallback check (if LLM returned empty string)
        return clean_title if clean_title else "Medical Consultation"

    except Exception as e:
        # 6. Observability: Log the error so you know if Groq fails
        print(f"⚠️ [Title Generation Error]: {str(e)}")
        return "Medical Consultation"