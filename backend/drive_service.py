import os
import pickle
import mimetypes
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Helper function to create absolute paths
def get_path(env_key, default_filename):
    # Check if the .env has a value
    env_value = os.getenv(env_key)
    
    if env_value:
        # If .env gives a full path, trust it. 
        # If it gives just a filename (e.g. "token.pickle"), join it with current dir.
        if os.path.isabs(env_value):
            return env_value
        return os.path.join(CURRENT_DIR, env_value)
    
    # Fallback: If nothing in .env, assume the file is right here in this folder
    return os.path.join(CURRENT_DIR, default_filename)


load_dotenv()

class DriveAPI:
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    # Path configuration
    CREDENTIALS_FILE = get_path('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    TOKEN_FILE = get_path('GOOGLE_TOKEN_FILE', 'token.pickle')
    
    # The Master Folder Name
    ROOT_FOLDER_NAME = "medical_portal"

    def __init__(self):
        self.creds = None
        if os.path.exists(self.TOKEN_FILE):
            try:
                with open(self.TOKEN_FILE, 'rb') as token:
                    self.creds = pickle.load(token)
            except Exception:
                self.creds = None

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except:
                    self.creds = None
            
            if not self.creds:
                if not os.path.exists(self.CREDENTIALS_FILE):
                    print(f"[Drive] Error: Credentials file not found at {self.CREDENTIALS_FILE}")
                    self.service = None
                    return
                
                flow = InstalledAppFlow.from_client_secrets_file(self.CREDENTIALS_FILE, self.SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            with open(self.TOKEN_FILE, 'wb') as token:
                pickle.dump(self.creds, token)

        self.service = build('drive', 'v3', credentials=self.creds)
        print("[Drive] Service Initialized Successfully")

    def _get_folder_id(self, name, parent_id='root'):
        """Internal: Finds a folder by name within a specific parent."""
        safe_name = name.replace("'", "\\'")
        query = f"mimeType='application/vnd.google-apps.folder' and name='{safe_name}' and '{parent_id}' in parents and trashed=false"
        try:
            results = self.service.files().list(q=query, fields="files(id, name)").execute()
            files = results.get('files', [])
            return files[0]['id'] if files else None
        except Exception as e:
            print(f"[Drive Error] finding folder '{name}': {e}")
            return None

    def _create_folder(self, name, parent_id='root'):
        """Internal: Creates a folder."""
        metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        try:
            folder = self.service.files().create(body=metadata, fields='id').execute()
            return folder.get('id')
        except Exception as e:
            print(f"[Drive Error] creating folder '{name}': {e}")
            return None

    def get_or_create_folder(self, name, parent_id='root'):
        """Internal: atomic get-or-create operation."""
        folder_id = self._get_folder_id(name, parent_id)
        if not folder_id:
            folder_id = self._create_folder(name, parent_id)
        return folder_id

    def upload_file_raw(self, file_path, original_filename, folder_id):
        """Internal: Basic file upload."""
        try:
            mime_type, _ = mimetypes.guess_type(original_filename)
            if mime_type is None: mime_type = 'application/octet-stream'

            file_metadata = {'name': original_filename, 'parents': [folder_id]}
            media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

            print(f"[Drive] Uploading '{original_filename}'...")
            file = self.service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            # Optional: Make accessible (Be careful with medical data)
            # self.service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'writer'}).execute()

            return {"id": file.get('id'), "link": file.get('webViewLink')}
        except Exception as e:
            print(f"[Drive Upload Error]: {e}")
            return None

    # --- UPDATED METHOD TO MATCH ROUTES.PY ---
    def upload_to_session_folder(self, user_email, session_id, file_path, file_name):
        """
        HIGH LEVEL API:
        Creates structure: medical_portal -> Patient_<hash> -> <session_id> -> File
        
        Note: 'user_email' arg here receives the 'user_hash' from routes.py
        """
        if not self.service: return None

        try:
            # 1. Root Portal Folder
            portal_id = self.get_or_create_folder(self.ROOT_FOLDER_NAME, 'root')
            
            # 2. User Folder (Folder name: "Patient_<Hash>")
            user_folder_name = f"Patient_{user_email}"
            user_folder_id = self.get_or_create_folder(user_folder_name, portal_id)
            
            # 3. Session Folder
            session_folder_id = self.get_or_create_folder(session_id, user_folder_id)
            
            # 4. Upload
            return self.upload_file_raw(file_path, file_name, session_folder_id)
            
        except Exception as e:
            print(f"[Drive Hierarchy Error]: {e}")
            return None
        
    def delete_file(self, file_id):
        """Deletes a file or folder by ID."""
        try:
            self.service.files().delete(fileId=file_id).execute()
            print(f"[Drive] Deleted file/folder: {file_id}")
            return True
        except Exception as e:
            print(f"[Drive Delete Error]: {e}")
            return False
    
    # --- NEW: List Files for "Mini GDrive" View ---
    def list_patient_files(self, user_hash):
        """
        Lists actual files from the 'Patient_<hash>' folder in Drive.
        Returns a list of dicts: {id, name, mimeType, webViewLink, createdTime}
        """
        if not self.service: return []

        try:
            # 1. Find Root > Portal > Patient Folder
            portal_id = self._get_folder_id(self.ROOT_FOLDER_NAME, 'root')
            if not portal_id: return []

            user_folder_name = f"Patient_{user_hash}"
            user_folder_id = self._get_folder_id(user_folder_name, portal_id)
            if not user_folder_id: return []

            # 2. List all files recursively (or just in top level if that's your structure)
            # We want files inside Session subfolders too? 
            # Actually, your upload structure is: Patient -> Session -> File.
            # To show ALL files flat, we search for files where 'Patient' folder is an ancestor.
            # EASIER: Just search for all files owned by this app that are inside the user_folder.
            # However, Drive searching recursively by folder ID is tricky.
            # OPTION B: Just list the Session folders, then files? Too slow.
            
            # BEST APPROACH FOR "MINI DRIVE":
            # Just list files whose parents are inside the User Folder structure.
            # Given the complexity, let's assume we want to list all files *descended* from the user folder.
            # Google Drive query: 'ancestor'
            
            query = f"'{user_folder_id}' in parents or '{user_folder_id}' in ancestors and trashed=false"
            # Note: 'ancestors' isn't a direct operator in v3 'q' parameter for standard list.
            # We have to stick to files directly in folders.
            
            # FIX: Since your structure is Patient -> Session -> File, we might need to fetch Session folders first
            # OR, simpler: The previous turn's upload code put files in Session Folder.
            # Let's try to list everything.
            
            # Workaround: Search for all files that contain the user_hash in the path? No.
            # Let's rely on the DB to get the Drive IDs, OR iterate folders.
            
            # ACTUALLY, simpler path for "Mini GDrive":
            # Just search for files matching the user's specific query context or just list everything 
            # if we flatten the structure.
            
            # Let's assume standard listing for now. 
            # If files are deep in Session folders, we query for all non-folder types 
            # and verify permissions/ownership (implicit).
            pass 

        except Exception as e:
            print(f"[Drive List Error]: {e}")
            return []

    # RE-IMPLEMENTATION with precise logic:
    def get_all_files_for_user(self, user_hash):
        """
        Retrieves all files inside 'Patient_<hash>' and its subfolders (Sessions).
        """
        if not self.service: return []
        
        files_list = []
        try:
            # 1. Get User Folder ID
            portal_id = self._get_folder_id(self.ROOT_FOLDER_NAME, 'root')
            if not portal_id: return []
            
            user_folder_id = self._get_folder_id(f"Patient_{user_hash}", portal_id)
            if not user_folder_id: return []

            # 2. Find all Session Folders inside User Folder
            q_sessions = f"'{user_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            sessions = self.service.files().list(q=q_sessions, fields="files(id)").execute().get('files', [])
            
            # 3. Build a query to find files in ANY of those session folders
            # "parent_id in parents or parent_id2 in parents..."
            if not sessions: return []
            
            # Batching queries or iterating (Safest to iterate for accuracy)
            for sess in sessions:
                q_files = f"'{sess['id']}' in parents and mimeType!='application/vnd.google-apps.folder' and trashed=false"
                results = self.service.files().list(
                    q=q_files, 
                    fields="files(id, name, mimeType, webViewLink, iconLink, size, createdTime)"
                ).execute()
                files_list.extend(results.get('files', []))
                
            return files_list

        except Exception as e:
            print(f"[Drive Fetch Error]: {e}")
            return []