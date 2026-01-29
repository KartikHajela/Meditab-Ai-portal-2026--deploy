from google import genai
from google.genai import types
import os
import time
from dotenv import load_dotenv

# 1. Load Environment Variables
load_dotenv()

# 2. Setup Client
API_KEY = os.getenv("gemini_api_key")
if not API_KEY:
    raise ValueError("Missing 'gemini_api_key' in .env file")

client = genai.Client(api_key=API_KEY)

# --- SYSTEM INSTRUCTIONS ---
# These guide the AI's behavior in every chat session
SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant for a Patient Portal. 
Your goal is to gather information from the patient to prepare a summary for the real doctor.

RULES:
1. Be empathetic, professional, and clear.
2. When a user describes symptoms, ask 1-2 relevant follow-up questions.
3. DO NOT provide a medical diagnosis. Instead, say "This sounds like something the doctor should review."
4. If the user types 'SUMMARIZE', you must stop chatting and output a STRICT JSON summary.
"""

def get_ai_response(db_history: list, new_user_message: str) -> str:
    """
    Handles the chat logic:
    1. Converts Database History (role/content) -> Gemini SDK Format
    2. Creates a chat session with system instructions
    3. Sends the new user message and returns the text response
    """
    chat_history = []
    
    # Adapt to your database schema ('role' and 'content' keys)
    # This loop ensures the AI remembers what was said previously
    for msg in db_history:
        # DB 'user' -> SDK 'user'; DB 'assistant' -> SDK 'model'
        role = "user" if msg.get("role") == "user" else "model"
        if msg.get("content"): 
            chat_history.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["content"])]
            ))

    # Step B: Create Chat Session with modern 2.0 Flash model
    chat = client.chats.create(
        model="gemini-2.5-flash", 
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
        history=chat_history
    )
    
    # Step C: Send Message and return response
    try:
        response = chat.send_message(new_user_message)
        return response.text
    except Exception as e:
        print(f"Chat API Error: {str(e)}")
        return f"I'm having trouble connecting to my brain right now. Error: {str(e)}"

def transcribe_audio(file_path: str) -> str:
    """
    Handles audio processing:
    1. Uploads audio file to Gemini
    2. Polls status until processing is complete
    3. Sends a Hinglish transcription prompt and returns the result
    """
    try:
        print(f"Uploading {file_path} to Gemini...")
        upload_result = client.files.upload(file=file_path)
        
        # Poll for processing completion
        while upload_result.state.name == "PROCESSING":
            print("Audio is being processed...")
            time.sleep(2) # Wait 2 seconds before checking again
            upload_result = client.files.get(name=upload_result.name)

        if upload_result.state.name == "FAILED":
            return "Audio processing failed by Gemini."

        print("Audio ready. Generating Hinglish transcript...")

        # Prompt for Hinglish transcription
        prompt = "Listen to this audio. Transcribe exactly what is said in Hindi, but write it using the English alphabet (Hinglish/Roman Script). Example: 'Tum kaise ho?'"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=upload_result.uri,
                            mime_type=upload_result.mime_type
                        ),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ]
        )
        return response.text

    except Exception as e:
        print(f"Transcription Error: {str(e)}")
        return f"Error processing audio: {str(e)}"