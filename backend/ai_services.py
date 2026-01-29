import os
import json
from dotenv import load_dotenv
from groq import AsyncGroq

# 1. Load Environment Variables
load_dotenv()

# 2. Setup Client
API_KEY = os.getenv("groq_api_key")
if not API_KEY:
    raise ValueError("Missing 'groq_api_key' in .env file")

# Initialize Async Client
client = AsyncGroq(api_key=API_KEY)

# --- CONFIGURATION ---
CHAT_MODEL = "llama-3.3-70b-versatile"
AUDIO_MODEL = "whisper-large-v3"

SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant for a Patient Portal. 
Your goal is to gather information from the patient to prepare a summary for the real doctor.

RULES:
1. Be empathetic, professional, and clear.
2. When a user describes symptoms, ask 1-2 relevant follow-up questions.
3. DO NOT provide a medical diagnosis. Instead, say "This sounds like something the doctor should review."
4. If the user types 'SUMMARIZE', you must stop chatting and output a STRICT JSON summary.
"""

async def get_ai_response(db_history: list, new_user_message: str) -> str:
    """
    Handles the chat logic using Groq:
    1. Converts Database History -> Groq Messages Format
    2. Sends request to Llama 3.3
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    
    # 1. Format History
    for msg in db_history:
        # DB 'user'/'assistant' -> Groq roles
        role = msg.get("role")
        content = msg.get("content")

        if isinstance(content, list): 
            content = " ".join([str(p) for p in content])
        
        if role and content:
            messages.append({"role": role, "content": content})

    # 2. Append New Message
    messages.append({"role": "user", "content": new_user_message})

    try:
        completion = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.6,
            max_tokens=1024
        )
        return completion.choices[0].message.content
    except Exception as e:
        print(f"Groq Chat Error: {str(e)}")
        return f"I'm having trouble connecting to my brain right now. Error: {str(e)}"

async def transcribe_audio(file_path: str) -> str:
    """
    Handles audio processing like test_groc.py:
    1. Whisper: Audio -> Hindi/Source Text
    2. Llama: Source Text -> Hinglish (Roman Script)
    """
    try:
        # Step 1: Transcribe with Whisper
        print(f"Transcribing {file_path}...")
        with open(file_path, "rb") as file:
            transcription = await client.audio.transcriptions.create(
                file=(file_path, file.read()),
                model=AUDIO_MODEL,
                language="hi", # Hinting Hindi improves accuracy for Indian context
                response_format="json"
            )
        raw_text = transcription.text
        
        # Step 2: Convert to Hinglish using Llama
        # We use a specialized prompt for script conversion
        print("Converting to Hinglish...")
        conversion = await client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": "You are a translator. Convert the following Hindi/Indian language text into Hinglish (Roman Script) exactly as it sounds. Do not translate the meaning to English, just the script. Output ONLY the converted text."
                },
                {"role": "user", "content": raw_text}
            ],
            temperature=0.1
        )
        
        return conversion.choices[0].message.content.strip()

    except Exception as e:
        print(f"Audio Processing Error: {str(e)}")
        return f"Error processing audio: {str(e)}"