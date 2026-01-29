import os
import time
import json
import random
from typing import TypedDict, Annotated, List, Literal, Optional
import operator
from datetime import datetime

# --- LIBRARIES ---
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.prompt import Prompt

# --- AI CORE ---
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, Field

# --- CONFIGURATION ---
load_dotenv()
if not os.getenv("GROQ_API_KEY"):
    raise ValueError("❌ MISSING API KEY: Please set GROQ_API_KEY in your .env file")

# Initialize Rich Console
console = Console()

# --- 1. VISUALIZATION UTILITIES (Studio Quality UI) ---

def print_header():
    """Renders the application header."""
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="right")
    grid.add_row(
        "[bold cyan]🏥 MEDITAB: AI PATIENT PORTAL[/bold cyan]", 
        "[dim]v2.5.0 | Powered by Groq LPU™[/dim]"
    )
    console.print(Panel(grid, style="cyan on black"))

def print_agent_thought(agent_name: str, thought: str):
    """Renders internal AI reasoning nicely."""
    console.print(f"[dim italic] 🧠 {agent_name} is thinking: {thought}...[/dim italic]")

def print_tool_usage(tool_name: str, input_data: str):
    """Visualizes a tool being triggered."""
    console.print(f"[bold yellow] 🛠️  Tool Triggered:[/bold yellow] [cyan]{tool_name}[/cyan] [dim]({input_data})[/dim]")

def print_ai_response(text: str):
    """Renders the final AI speech."""
    console.print(Panel(Text(text, style="green"), title="[bold]Dr. AI[/bold]", title_align="left", border_style="green"))

def print_critical_alert(message: str):
    """Renders emergency alerts."""
    console.print(Panel(f"[blink bold white on red] 🚨 CRITICAL ALERT: {message} [/blink bold white on red]", border_style="red"))

# --- 2. DATA MODELS (Strict Schemas) ---

class Vitals(BaseModel):
    heart_rate: Optional[int] = Field(None, description="Heart Rate in BPM")
    bp_systolic: Optional[int] = Field(None, description="Systolic Blood Pressure (top number)")
    bp_diastolic: Optional[int] = Field(None, description="Diastolic Blood Pressure (bottom number)")
    temp_c: Optional[float] = Field(None, description="Body Temperature in Celsius")

class ClinicalSummary(BaseModel):
    """The Gold Standard Medical Summary"""
    patient_id: str = Field(description="Unique Patient Identifier")
    visit_type: Literal["Routine", "Urgent", "Follow-up"]
    chief_complaint: str = Field(description="The primary reason for the visit")
    hpi: str = Field(description="History of Present Illness - detailed narrative")
    detected_vitals: Vitals = Field(description="Any vitals extracted from conversation")
    medication_plan: List[str] = Field(description="Suggested medications or changes")
    follow_up_required: bool = Field(description="Does the patient need to see a human doctor?")
    risk_level: Literal["Low", "Moderate", "Critical"]

# --- 3. TOOLS (The "Arms & Legs" of the Agent) ---

@tool
def search_patient_records(query_name: str) -> str:
    """Searches the 'Vector DB' for patient history."""
    time.sleep(1) # Simulate network latency for realism
    # Mock Database
    mock_db = {
        "john doe": "PATIENT: John Doe (M, 45). Hx: Hypertension, Type 2 Diabetes. Last Visit: 3 months ago. Meds: Metformin, Lisinopril.",
        "sarah smith": "PATIENT: Sarah Smith (F, 29). Hx: Asthma. Allergies: Penicillin.",
    }
    result = mock_db.get(query_name.lower(), "No record found. Create new profile.")
    return f" [DATABASE RETURN] {result}"

@tool
def check_drug_interaction(drug_a: str, drug_b: str) -> str:
    """Checks for contraindications between two medications."""
    time.sleep(0.8)
    interactions = {
        ("aspirin", "warfarin"): "CRITICAL: Increased bleeding risk.",
        ("lisinopril", "ibuprofen"): "MODERATE: May reduce anti-hypertensive effect.",
    }
    pair = tuple(sorted([drug_a.lower(), drug_b.lower()]))
    return interactions.get(pair, "SAFE: No known major interactions.")

@tool
def scan_uploaded_document(doc_type: str) -> str:
    """Simulates OCR scanning of a user-uploaded file (PDF/Image)."""
    time.sleep(1.5)
    if "lab" in doc_type.lower():
        return "OCR SCAN RESULT: [Lab Report: CBC] WBC: 12.5 (High), RBC: Normal. Platelets: Normal."
    return "OCR SCAN RESULT: [Unknown Document] Text unclear."

@tool
def schedule_appointment(department: str, urgency: str) -> str:
    """Books a slot in the hospital system."""
    return f"SUCCESS: Appointment booked in {department} (Priority: {urgency}) for tomorrow at 10:00 AM."

# --- 4. STATE MANAGEMENT (The "Brain") ---

class GlobalState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    patient_profile: Optional[str]
    triage_status: Literal["unknown", "stable", "critical"]
    current_agent: str

# --- 5. AGENT NODE DEFINITIONS ---

# Initialize LLM
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.3)

# -- A. THE TRIAGE AGENT (The Router) --
def triage_node(state: GlobalState):
    """Analyzes the FIRST input to decide who handles it."""
    last_msg = state["messages"][-1].content.lower()
    
    # Simple Heuristic Routing (can be replaced by LLM classifier)
    if any(x in last_msg for x in ["chest pain", "can't breathe", "fainted", "blood"]):
        return {"triage_status": "critical", "current_agent": "emergency"}
    elif any(x in last_msg for x in ["appointment", "schedule", "bill", "admin"]):
        return {"triage_status": "stable", "current_agent": "admin"}
    else:
        return {"triage_status": "stable", "current_agent": "clinical"}

# -- B. THE CLINICAL AGENT (Doctor) --
def clinical_agent_node(state: GlobalState):
    """The main medical interviewer."""
    
    # 1. Bind Tools
    my_tools = [search_patient_records, check_drug_interaction, scan_uploaded_document]
    model_with_tools = llm.bind_tools(my_tools)
    
    # 2. System Persona
    persona = """You are Dr. Nexus, an advanced AI clinician.
    - Your goal is to gather a complete History of Present Illness (HPI).
    - If the user mentions past history, USE 'search_patient_records'.
    - If the user mentions uploading a lab/doc, USE 'scan_uploaded_document'.
    - If the user mentions multiple meds, USE 'check_drug_interaction'.
    - Be professional but warm.
    - If you have enough info, type 'SUMMARY_READY' to end the session.
    """
    
    response = model_with_tools.invoke([SystemMessage(content=persona)] + state["messages"])
    return {"messages": [response]}

# -- C. THE ADMIN AGENT --
def admin_agent_node(state: GlobalState):
    """Handles logistics."""
    my_tools = [schedule_appointment]
    model_with_tools = llm.bind_tools(my_tools)
    
    persona = "You are the Hospital Admin. Help users book appointments or check bills. Use tools if needed."
    response = model_with_tools.invoke([SystemMessage(content=persona)] + state["messages"])
    return {"messages": [response]}

# -- D. THE SUMMARY GENERATOR (Strict JSON) --
def summary_node(state: GlobalState):
    """Compiles the final report."""
    structured_llm = llm.with_structured_output(ClinicalSummary)
    
    # We feed the whole history to the summarizer
    summary = structured_llm.invoke(state["messages"])
    
    # Pretty Print the Summary
    console.print("\n")
    console.rule("[bold green]✅ SESSION COMPLETE: GENERATING REPORT[/bold green]")
    
    # Create a nice table for the summary
    table = Table(title=f"Medical Summary: {summary.patient_id.upper()}")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Details", style="white")
    
    table.add_row("Chief Complaint", summary.chief_complaint)
    table.add_row("HPI", summary.hpi)
    table.add_row("Risk Level", f"[bold red]{summary.risk_level}[/bold red]" if summary.risk_level == "Critical" else summary.risk_level)
    table.add_row("Follow-up?", "YES" if summary.follow_up_required else "No")
    
    console.print(table)
    console.print(Panel(f"Rx Plan: {', '.join(summary.medication_plan)}", title="Plan", border_style="green"))
    
    return {"messages": [AIMessage(content="Report generated and sent to provider.")]}

# -- E. EMERGENCY OVERRIDE --
def emergency_node(state: GlobalState):
    print_critical_alert("CRITICAL SYMPTOMS DETECTED. DISPATCHING EMERGENCY PROTOCOL.")
    return {"messages": [AIMessage(content="I have flagged your location for emergency services. Please remain calm. A human operator is taking over.")]}

# --- 6. GRAPH ORCHESTRATION ---

workflow = StateGraph(GlobalState)

# Add Nodes
workflow.add_node("triage", triage_node)
workflow.add_node("clinical", clinical_agent_node)
workflow.add_node("admin", admin_agent_node)
workflow.add_node("emergency", emergency_node)
workflow.add_node("tools", ToolNode([search_patient_records, check_drug_interaction, scan_uploaded_document, schedule_appointment]))
workflow.add_node("summarizer", summary_node)

# Entry Point
workflow.set_entry_point("triage")

# Conditional Edges (The Logic)
def route_after_triage(state):
    return state["current_agent"] # Returns 'clinical', 'admin', or 'emergency'

workflow.add_conditional_edges("triage", route_after_triage)

def route_medical_step(state):
    last_msg = state["messages"][-1]
    
    # 1. If Tool Call -> Go to Tools
    if last_msg.tool_calls:
        return "tools"
    
    # 2. If Summary Keyword -> Go to Summary
    if "SUMMARY_READY" in last_msg.content:
        return "summarizer"
        
    # 3. Else -> Loop back to User (End this turn)
    return END

workflow.add_conditional_edges("clinical", route_medical_step)
workflow.add_conditional_edges("admin", route_medical_step)

# Tool Outputs loop back to the agent who called them
workflow.add_edge("tools", "clinical") 
workflow.add_edge("emergency", END)
workflow.add_edge("summarizer", END)

app = workflow.compile()

# --- 7. THE STUDIO RUNTIME LOOP ---

def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print_header()
    
    history = []
    
    # Initial Greeting
    console.print("[bold green]Dr. AI:[/bold green] Hello. I am Med-Nexus. You can speak naturally, upload docs (type 'upload [file]'), or ask for appointments.")
    
    while True:
        try:
            # Studio-style Input
            user_input = Prompt.ask("\n[bold cyan]User[/bold cyan]")
            if user_input.lower() in ["exit", "quit", "q"]:
                console.print("[dim]Shutting down system...[/dim]")
                break
            
            # Simulated Processing Spinner
            with Live(Spinner("dots", text="[bold cyan]Med-Nexus is analyzing...[/bold cyan]"), refresh_per_second=10, transient=True):
                # 1. Run the Graph
                history.append(HumanMessage(content=user_input))
                final_state = app.invoke({"messages": history})
                history = final_state["messages"]
                
                # 2. Extract Response
                last_msg = history[-1]
                
                # If we just finished a summary, reset or exit
                if "Report generated" in str(last_msg.content):
                    break 

            # 3. Render Response (Cleanly)
            if isinstance(last_msg, AIMessage):
                # Clean up the "SUMMARY_READY" token if it appears
                clean_text = last_msg.content.replace("SUMMARY_READY", "")
                if clean_text.strip():
                    print_ai_response(clean_text)
                    
        except Exception as e:
            console.print(f"[bold red]SYSTEM ERROR:[/bold red] {e}")
            break

if __name__ == "__main__":
    main()