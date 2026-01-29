import asyncio
import os
import time
import json
import tempfile
import threading
import queue
import sys

# Third-party libraries
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from pynput import keyboard
from dotenv import load_dotenv
from groq import AsyncGroq

# Load Env
load_dotenv()
API_KEY = os.getenv("groq_api_key")
if not API_KEY:
    raise ValueError("Missing 'groq_api_key' in .env file")

# --- CONFIGURATION ---
SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant for a Patient Portal. 
Your goal is to gather information from the patient to prepare a summary for the real doctor.

RULES:
1. Be empathetic, professional, and clear.
2. When a user describes symptoms, ask 1-2 relevant follow-up questions.
3. DO NOT provide a medical diagnosis. Instead, say "This sounds like something the doctor should review."
4. If the user types 'SUMMARIZE', you must stop chatting and output a STRICT JSON summary.
"""

SAMPLE_RATE = 44100  # Hz
CHANNELS = 1

# --- AUDIO RECORDING UTILITIES ---

class AudioRecorder:
    """
    Handles Start/Stop recording via Hotkeys.
    """
    def __init__(self):
        self.recording = False
        self.audio_frames = []
        self.stop_event = threading.Event()
        self.input_queue = queue.Queue()

    def callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if self.recording:
            self.audio_frames.append(indata.copy())

    def record_until_key(self):
        """
        Blocking function:
        1. Waits for user to press SPACE to start.
        2. Records until user releases SPACE (or presses it again depending on logic).
        For this implementation: Press SPACE to Start, Press SPACE again to Stop.
        """
        print("\n[INFO] Press 'SPACE' to START recording...")
        
        # Listener for start
        with keyboard.Listener(on_press=self.on_press_start) as listener:
            listener.join()
        
        print("[REC] Recording... Press 'SPACE' to STOP.")
        self.recording = True
        self.audio_frames = []

        # Start stream
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, callback=self.callback):
            # Listener for stop
            with keyboard.Listener(on_press=self.on_press_stop) as listener:
                listener.join()
        
        self.recording = False
        print("[INFO] Processing audio...")

        # Process raw data
        if not self.audio_frames:
            return None
            
        recording_array = np.concatenate(self.audio_frames, axis=0)
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            wav.write(temp_wav.name, SAMPLE_RATE, recording_array)
            return temp_wav.name

    def on_press_start(self, key):
        if key == keyboard.Key.space:
            return False # Stop listener, move to recording phase

    def on_press_stop(self, key):
        if key == keyboard.Key.space:
            return False # Stop listener, end recording

# --- ASYNC LOGIC ---

async def transcribe_and_convert(client: AsyncGroq, filepath: str) -> str:
    """
    1. Whisper: Audio -> Hindi Text (Devanagari)
    2. Llama: Hindi Text -> Hinglish (Roman)
    """
    try:
        # Step 1: Transcribe
        with open(filepath, "rb") as file:
            transcription = await client.audio.transcriptions.create(
                file=(filepath, file.read()),
                model="whisper-large-v3",
                language="hi", # Guide it towards Hindi
                response_format="json"
            )
        raw_text = transcription.text
        
        # Step 2: Convert to Hinglish
        # We use a fast model for this simple translation task
        conversion = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a translator. Convert the following Hindi/any indian language including english text into Hinglish (Roman Script) exactly as it sounds. Do not translate the meaning to English, just the script. Output ONLY the converted text."},
                {"role": "user", "content": raw_text}
            ],
            temperature=0.1
        )
        return conversion.choices[0].message.content.strip()
    
    except Exception as e:
        return f"Error processing audio: {e}"
    finally:
        # Cleanup temp file
        if os.path.exists(filepath):
            os.remove(filepath)

async def main():
    client = AsyncGroq(api_key=API_KEY)
    recorder = AudioRecorder()
    
    # Initialize Chat History with System Prompt
    chat_history = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    print("--- Medical AI Assistant Online ---")
    print("Commands: Type 'quit' to exit | Type 'rec' to capture voice.")

    while True:
        try:
            # 1. Get User Input
            # We use a standard input, but allow a special command 'rec' to trigger the hotkey recorder
            user_input = await asyncio.to_thread(input, "\nUser (type 'rec' for audio): ")
            user_input = user_input.strip()

            if user_input.lower() == "quit":
                print("Terminating session...")
                break

            # 2. Handle Audio Input
            if user_input.lower() == "rec":
                # Trigger the hotkey recorder logic
                audio_file = await asyncio.to_thread(recorder.record_until_key)
                if audio_file:
                    print("Transcribing (Whisper) + Converting (Llama)...")
                    user_input = await transcribe_and_convert(client, audio_file)
                    print(f"Detected Voice: {user_input}")
                else:
                    print("No audio recorded.")
                    continue

            # 3. Add to History
            chat_history.append({"role": "user", "content": user_input})

            # 4. Stream Response from Groq
            print("AI: ", end="", flush=True)
            
            stream = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=chat_history,
                temperature=0.6,
                max_tokens=1024,
                stream=True
            )

            full_response = ""
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    print(content, end="", flush=True)
                    full_response += content
            
            print() # Newline after stream ends

            # 5. Update History
            chat_history.append({"role": "assistant", "content": full_response})

            # 6. Check for Summary Trigger (Client-side check to create file)
            if "SUMMARIZE" in user_input.upper():
                try:
                    # The AI should have outputted JSON. Let's try to parse the last message.
                    # Note: Llama might wrap it in ```json blocks.
                    clean_json = full_response.replace("```json", "").replace("```", "").strip()
                    summary_data = json.loads(clean_json)
                    print(f"\n[SYSTEM] Summary Generated & Validated: {summary_data.keys()}")
                    # Break or Continue based on preference. Let's break as per 'stop chatting' rule.
                    break 
                except json.JSONDecodeError:
                    pass 

        except KeyboardInterrupt:
            print("\nForce Quit.")
            break
        except Exception as e:
            print(f"\n[ERROR] Loop error: {e}")

if __name__ == "__main__":
    asyncio.run(main())