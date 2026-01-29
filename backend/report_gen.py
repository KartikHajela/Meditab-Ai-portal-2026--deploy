# ... (Keep existing imports: os, json, time, etc.)

# --- PDF GENERATION IMPORTS ---


# ==========================================
# 3. PDF GENERATOR ENGINE (PROFESSIONAL TEMPLATE)
# ==========================================

class MedicalReportGenerator:
    @staticmethod
    def create_pdf(filename: str, data: dict):
        file_path = os.path.join(REPORTS_DIR, filename)
        doc = SimpleDocTemplate(file_path, pagesize=A4, 
                                rightMargin=40, leftMargin=40, 
                                topMargin=40, bottomMargin=40)
        
        styles = getSampleStyleSheet()
        
        # --- CUSTOM STYLES (Heidi/Modern Style) ---
        # Main Title
        styles.add(ParagraphStyle(name='ReportTitle', parent=styles['Heading1'], 
                                fontSize=22, textColor=colors.HexColor('#1e293b'), 
                                fontName='Helvetica-Bold', spaceAfter=20))
        
        # Section Headers (Blue background strip)
        styles.add(ParagraphStyle(name='SectionHeader', parent=styles['Normal'], 
                                fontSize=11, textColor=colors.white, backColor=colors.HexColor('#0e7490'), 
                                fontName='Helvetica-Bold', borderPadding=(6, 10, 6, 10), 
                                spaceBefore=15, spaceAfter=10))
        
        # Subsection / Labels
        styles.add(ParagraphStyle(name='SubHeader', parent=styles['Heading3'], 
                                fontSize=10, textColor=colors.HexColor('#0e7490'), 
                                fontName='Helvetica-Bold', spaceAfter=4))
        
        # Data/Body Text
        styles.add(ParagraphStyle(name='BodyText', parent=styles['Normal'], 
                                fontSize=10, leading=14, textColor=colors.HexColor('#334155')))
        
        # Small Labels for tables
        styles.add(ParagraphStyle(name='Label', parent=styles['Normal'], 
                                fontSize=8, textColor=colors.HexColor('#64748b')))
        
        story = []

        # --- 1. HEADER & LOGO AREA ---
        # (Text based logo for now, can be replaced with Image)
        story.append(Paragraph("MEDITAB", ParagraphStyle(name='Brand', parent=styles['Normal'], fontSize=14, textColor=colors.HexColor('#0e7490'), fontName='Helvetica-Bold')))
        story.append(Paragraph("Secure Health Portal Report", styles['Label']))
        story.append(Spacer(1, 20))

        story.append(Paragraph(f"MEDICAL REPORT: {data.get('patient_name', 'Unknown').upper()}", styles['ReportTitle']))

        # --- 2. ADMINISTRATIVE DETAILS (Grid) ---
        req_date = datetime.now().strftime("%d/%m/%Y")
        
        # Row 1: Patient Name | DOB
        # Row 2: Date | Ref ID
        admin_data = [
            [Paragraph("PATIENT NAME", styles['Label']), Paragraph("DATE OF REPORT", styles['Label'])],
            [Paragraph(data.get('patient_name', 'Unknown'), styles['BodyText']), Paragraph(req_date, styles['BodyText'])],
            
            [Paragraph("DOCTOR / PROVIDER", styles['Label']), Paragraph("REPORT ID", styles['Label'])],
            [Paragraph("Dr. AI Assistant (MD, FRACGP)", styles['BodyText']), Paragraph(str(int(time.time()))[-6:], styles['BodyText'])]
        ]
        
        admin_table = Table(admin_data, colWidths=[3.5*inch, 3.5*inch])
        admin_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,1), (-1,1), 1, colors.HexColor('#e2e8f0')), # Line after first data row
            ('LINEBELOW', (0,3), (-1,3), 1, colors.HexColor('#e2e8f0')), # Line after second data row
            ('BOTTOMPADDING', (0,0), (-1,-1), 12),
            ('TOPPADDING', (0,0), (-1,-1), 12),
        ]))
        story.append(admin_table)
        story.append(Spacer(1, 10))

        # --- 3. SUBJECTIVE FINDINGS ---
        story.append(Paragraph("SUBJECTIVE FINDINGS", styles['SectionHeader']))
        
        story.append(Paragraph("Presenting Complaint", styles['SubHeader']))
        story.append(Paragraph(data.get("chief_complaint", "N/A"), styles['BodyText']))
        story.append(Spacer(1, 8))
        
        story.append(Paragraph("History & Context", styles['SubHeader']))
        story.append(Paragraph(data.get("history", "N/A"), styles['BodyText']))
        story.append(Spacer(1, 15))

        # --- 4. OBJECTIVE FINDINGS (Table Style) ---
        story.append(Paragraph("OBJECTIVE FINDINGS & ASSESSMENT", styles['SectionHeader']))
        
        # Table Header
        obj_data = [[Paragraph("CLINICAL ASSESSMENT / DIAGNOSIS", styles['SubHeader'])]]
        # Table Content
        obj_data.append([Paragraph(data.get("diagnosis", "Pending Review"), styles['BodyText'])])
        
        obj_table = Table(obj_data, colWidths=[7*inch])
        obj_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')), # Light gray header
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0,0), (-1,-1), 12),
        ]))
        story.append(obj_table)
        story.append(Spacer(1, 15))

        # --- 5. MANAGEMENT PLAN ---
        story.append(Paragraph("MANAGEMENT PLAN", styles['SectionHeader']))
        
        # Medications
        if data.get("medications"):
            story.append(Paragraph("Rx / Medications", styles['SubHeader']))
            for med in data['medications']:
                story.append(Paragraph(f"• {med}", styles['BodyText']))
            story.append(Spacer(1, 8))

        # Recommendations/Plan
        story.append(Paragraph("Recommendations & Next Steps", styles['SubHeader']))
        story.append(Paragraph(data.get("recommendations", "Follow up as required."), styles['BodyText']))
        story.append(Spacer(1, 30))

        # --- 6. SIGNATURE BLOCK ---
        sig_data = [
            [Paragraph("Electronically Signed By:", styles['Label']), Paragraph("Date Signed:", styles['Label'])],
            [Paragraph("<b>Dr. AI Assistant</b><br/>Meditab Medical Center", styles['BodyText']), Paragraph(req_date, styles['BodyText'])]
        ]
        sig_table = Table(sig_data, colWidths=[4*inch, 3*inch])
        sig_table.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,0), 2, colors.HexColor('#0e7490')), # Thick blue line above
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 15),
        ]))
        story.append(sig_table)
        
        # --- 7. DISCLAIMER FOOTER ---
        story.append(Spacer(1, 40))
        disclaimer = "This report is generated by Meditab AI based on provided session data. It does not replace professional medical advice. Please verify all information with primary clinical records."
        story.append(Paragraph(disclaimer, ParagraphStyle(name='Footer', parent=styles['Normal'], fontSize=7, textColor=colors.gray, alignment=TA_CENTER)))

        doc.build(story)
        return file_path

@tool
def generate_hospital_pdf(patient_name: str, chief_complaint: str, history: str, diagnosis: str, medications: str, recommendations: str):
    """
    Generates a formal PDF medical report. 
    Use this tool ONLY when the user asks for a summary, final report, or discharge paper.
    medications input should be a comma-separated string.
    """
    filename = f"Report_{int(time.time())}.pdf"
    med_list = [m.strip() for m in medications.split(',')]
    
    data = {
        "patient_name": patient_name,
        "chief_complaint": chief_complaint,
        "history": history,
        "diagnosis": diagnosis,
        "medications": med_list,
        "recommendations": recommendations
    }
    
    path = MedicalReportGenerator.create_pdf(filename, data)
    return f"REPORT_GENERATED_AT: /static/reports/{filename}"

model_with_tools = llm.bind_tools([generate_hospital_pdf])
