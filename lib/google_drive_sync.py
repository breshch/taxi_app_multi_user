import os
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BACKUP_FILENAME = "taxi_backup.db"


class GoogleDriveSync:
    def __init__(self, credentials_path="credentials.json", token_path="token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None

    def authenticate(self):
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        self.service = build("drive", "v3", credentials=creds)

    def upload_backup(self, local_path):
        if not self.service:
            self.authenticate()

        query = f"name='{BACKUP_FILENAME}' and trashed=false"
        results = (
            self.service.files()
            .list(q=query, spaces="drive", fields="files(id)")
            .execute()
        )
        files = results.get("files", [])

        media = MediaFileUpload(local_path, mimetype="application/octet-stream")

        if files:
            self.service.files().update(
                fileId=files[0]["id"], media_body=media
            ).execute()
        else:
            file_metadata = {"name": BACKUP_FILENAME}
            self.service.files().create(
                body=file_metadata, media_body=media, fields="id"
            ).execute()
