import os
import pickle
import mimetypes
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

# Database imports (Assuming you have these setup based on your prompt)
from sqlalchemy.orm import Session
from models import User, ChatHistory  # Ensure these are imported from your actual models file

load_dotenv()

class DriveAPI:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    TOKEN_FILE = os.getenv('GOOGLE_TOKEN_FILE', 'token.pickle')
    ROOT_FOLDER_NAME = "medical_portal"

    def __init__(self):
        self.creds = None
        if os.path.exists(self.TOKEN_FILE):
            with open(self.TOKEN_FILE, 'rb') as token:
                self.creds = pickle.load(token)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(self.CREDENTIALS_FILE):
                    raise FileNotFoundError(f"Credentials file '{self.CREDENTIALS_FILE}' not found.")
                flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            with open(self.TOKEN_FILE, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('drive', 'v3', credentials=self.creds)

    def _get_folder_id(self, name, parent_id='root'):
        """Finds a folder by name within a specific parent."""
        query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed=false"
        try:
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            return files[0]['id'] if files else None
        except Exception as e:
            print(f"[Drive Error] finding folder '{name}': {e}")
            return None

    def _create_folder(self, name, parent_id='root'):
        """Creates a folder."""
        metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        try:
            folder = self.service.files().create(body=metadata, fields='id').execute()
            print(f"✅ Created Folder: {name}")
            return folder.get('id')
        except Exception as e:
            print(f"[Drive Error] creating folder '{name}': {e}")
            return None

    def get_or_create_folder(self, name, parent_id='root'):
        """Helper to get ID if exists, otherwise create."""
        folder_id = self._get_folder_id(name, parent_id)
        if not folder_id:
            folder_id = self._create_folder(name, parent_id)
        return folder_id

    def upload_file(self, file_path, original_filename, parent_id):
        """Uploads a file to the specific parent folder."""
        try:
            mime_type, _ = mimetypes.guess_type(original_filename)
            if mime_type is None: 
                mime_type = 'application/octet-stream'

            file_metadata = {
                'name': original_filename, 
                'parents': [parent_id]
            }
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

            print(f"⬆️ Uploading '{original_filename}'...")
            file = self.service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            # Optional: Make readable by anyone (Use with caution for medical data)
            # self.service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()

            return file.get('id'), file.get('webViewLink')
        except Exception as e:
            print(f"[Upload Error]: {e}")
            return None, None

    def upload_to_session_folder(self, user_email, session_id, file_path, file_name="document.pdf"):
        """
        Main Business Logic:
        1. Ensures 'medical_portal' exists.
        2. Ensures 'User_<email>' folder exists.
        3. Ensures 'Session_<id>' folder exists.
        4. Uploads file there.
        """
        # 1. Root Portal Folder
        portal_id = self.get_or_create_folder(self.ROOT_FOLDER_NAME, 'root')
        
        # 2. User Folder (using Email from DB)
        user_folder_name = f"User_{user_email}"
        user_id = self.get_or_create_folder(user_folder_name, portal_id)
        
        # 3. Session Folder (using Session ID from DB)
        # Note: ChatHistory table provided session_id, e.g., 'session_176830...'
        session_folder_id = self.get_or_create_folder(session_id, user_id)
        
        # 4. Upload File
        file_id, file_link = self.upload_file(file_path, file_name, session_folder_id)
        
        if file_id:
            print(f"🎉 Success! File uploaded to {self.ROOT_FOLDER_NAME}/{user_folder_name}/{session_id}/")
            return {
                "drive_file_id": file_id,
                "file_url": file_link,
                "session_id": session_id,
                "user_email": user_email
            }
        return None

# --- DATABASE HELPER FUNCTIONS ---

def get_session_info_from_db(db: Session, target_session_id: str):
    """
    Fetches User Email and verifies Session ID exists by joining Users and ChatHistory.
    """
    # SQL equivalent: 
    # SELECT u.email, ch.session_id 
    # FROM users u 
    # JOIN chat_history ch ON u.id = ch.patient_id 
    # WHERE ch.session_id = 'target_session_id'
    
    result = db.query(User.email, ChatHistory.session_id)\
               .join(ChatHistory, User.id == ChatHistory.patient_id)\
               .filter(ChatHistory.session_id == target_session_id)\
               .first()
               
    if result:
        return result.email, result.session_id
    return None, None

# --- EXAMPLE USAGE ---

if __name__ == "__main__":
    # 1. Setup Drive API
    drive = DriveAPI()
    
    # 2. Mocking the DB Fetch (Replace this with actual DB session usage)
    # In real usage: 
    # db = SessionLocal()
    # email, session_id = get_session_info_from_db(db, "session_1768307860347")
    
    # Simulating the data you showed in the images:
    # User ID 5 (admin@local.com) has session 'session_1768307860347'
    mock_email = "admin@local.com" 
    mock_session_id = "session_1768307860347"
    
    # 3. Define the file to upload
    file_path_on_disk = "C:\\Users\\kartik.hajela\\Downloads\\Ai Portal\\backend\\db.py" # Make sure this file exists locally
    
    # Create a dummy file for testing if it doesn't exist
    if not os.path.exists(file_path_on_disk):
        with open(file_path_on_disk, "w") as f: f.write("Medical Record Content")

    # 4. Execute Upload
    print(f"Starting upload for Patient: {mock_email}, Session: {mock_session_id}")
    result = drive.upload_to_session_folder(mock_email, mock_session_id, file_path_on_disk, "blood_test.pdf")
    
    if result:
        # 5. Here you would save 'result' data into your MedicalMedia table
        print("\n--- Data to save to MedicalMedia Table ---")
        print(result)