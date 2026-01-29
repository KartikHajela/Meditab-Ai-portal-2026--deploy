from __future__ import print_function
import pickle
import os
import io
import shutil
from mimetypes import MimeTypes
import sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

dict1={"user1":["session_1768307860347","session_1768312121281"],"user2":["session_1768540671980"],"user3":["session_1768313023435"]}

class DriveAPI:
    # Define scopes
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    # Load configuration from .env or fall back to defaults
    CREDENTIALS_FILE = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
    TOKEN_FILE = os.getenv('GOOGLE_TOKEN_FILE', 'token.pickle')

    def __init__(self):
        self.creds = None

        # Check if the token file exists using the env path
        if os.path.exists(self.TOKEN_FILE):
            with open(self.TOKEN_FILE, 'rb') as token:
                self.creds = pickle.load(token)

        # If no valid credentials are available, request the user to log in.
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                # Use the credentials file path from env
                if not os.path.exists(self.CREDENTIALS_FILE):
                    print(f"Error: Credentials file '{self.CREDENTIALS_FILE}' not found.")
                    return

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.CREDENTIALS_FILE, self.SCOPES)
                self.creds = flow.run_local_server(port=8000,open_browser=False)

            # Save the access token to the path defined in env
            with open(self.TOKEN_FILE, 'wb') as token:
                pickle.dump(self.creds, token)

        # Connect to the API service
        self.service = build('drive', 'v3', credentials=self.creds)

        # List first 10 files to verify connection
        results = self.service.files().list(
            pageSize=10, fields="files(id, name)").execute()
        items = results.get('files', [])

        print("Here's a list of files (first 10): \n")
        print(*items, sep="\n", end="\n\n")

    def FileDownload(self, file_id, file_name):
        try:
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            
            downloader = MediaIoBaseDownload(fh, request, chunksize=204800)
            done = False

            while not done:
                status, done = downloader.next_chunk()

            fh.seek(0)
            
            with open(file_name, 'wb') as f:
                shutil.copyfileobj(fh, f)

            print("File Downloaded")
            return True
        except Exception as e:
            print(f"Something went wrong: {e}")
            return False

    def FileUpload(self, filepath):
        try:
            name = filepath.split('/')[-1]
            # Handle cases where path uses backslashes (Windows)
            if '\\' in name:
                name = filepath.split('\\')[-1]
                
            mimetype = MimeTypes().guess_type(name)[0]
            if mimetype is None:
                mimetype = 'application/octet-stream' # Default fallback
            
            file_metadata = {'name': name}

            media = MediaFileUpload(filepath, mimetype=mimetype)
            
            file = self.service.files().create(
                body=file_metadata, media_body=media, fields='id').execute()
            
            print("File Uploaded.")
        
        except Exception as e:
            print(f"Can't Upload File: {e}")

    def create_folder(service, folder_name, parent_id=None):
        """
        Create a folder in Google Drive.
        :param service: Authenticated Drive API service instance
        :param folder_name: Name of the folder to create
        :param parent_id: Optional parent folder ID
        :return: Created folder ID
        """
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
       }
        if parent_id:
            file_metadata['parents'] = [parent_id]

        try:
            folder = service.files().create(body=file_metadata, fields='id').execute()
            print(f"✅ Folder '{folder_name}' created with ID: {folder.get('id')}")
            return folder.get('id')
        except HttpError as error:
            print(f"❌ An error occurred: {error}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        obj = DriveAPI()
        
        # Simple input validation
        try:
            i = int(input("Enter your choice:\n1 - Download file, 2- Upload File, 3- Create Folder, 4- Exit.\n"))
        except ValueError:
            i = 0

        if i == 1:
            f_id = input("Enter file id: ")
            f_name = input("Enter file name to save as: ")
            obj.FileDownload(f_id, f_name)
            
        elif i == 2:
            f_path = input("Enter full file path to upload: ")
            obj.FileUpload(f_path)
        
        elif i == 3:
            f_name = input("Enter folder name to create: ")
            parent_id = input("Enter parent folder ID (or press Enter for root): ")
            if parent_id.strip() == "":
                parent_id = None
            DriveAPI.create_folder(obj.service, f_name, parent_id)
        
        else:
            exit()
    except Exception as e:
        print(f"An error occurred initializing the API: {e}")