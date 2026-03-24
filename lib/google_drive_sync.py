"""
Модуль синхронизации с Google Drive
"""
import os
import json
from datetime import datetime
from typing import Optional, Tuple

class GoogleDriveSync:
    """Класс для синхронизации с Google Drive"""
    
    def __init__(self, credentials_path='credentials.json', token_path='token.json'):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.authenticated = False
        
    def check_credentials(self) -> Tuple[bool, str]:
        """Проверяет наличие credentials.json"""
        if not os.path.exists(self.credentials_path):
            return False, "❌ Файл credentials.json не найден"
        return True, "✅ credentials.json найден"
    
    def authenticate(self) -> Tuple[bool, str, Optional[str]]:
        """
        Авторизация в Google Drive
        Возвращает: (успех, сообщение, auth_url или None)
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            
            SCOPES = ['https://www.googleapis.com/auth/drive.file']
            
            # Проверяем credentials
            creds_check, creds_msg = self.check_credentials()
            if not creds_check:
                return False, creds_msg, None
            
            # Пробуем загрузить существующий токен
            if os.path.exists(self.token_path):
                try:
                    creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
                    if creds.valid:
                        self.service = self._build_service(creds)
                        self.authenticated = True
                        return True, "✅ Уже авторизовано", None
                    elif creds.expired and creds.refresh_token:
                        creds.refresh(self._get_request())
                        self._save_token(creds)
                        self.service = self._build_service(creds)
                        self.authenticated = True
                        return True, "✅ Токен обновлён", None
                except Exception as e:
                    os.remove(self.token_path) if os.path.exists(self.token_path) else None
            
            # Создаём новый flow
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path,
                SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
            
            return False, "⏳ Требуется авторизация", auth_url
            
        except Exception as e:
            return False, f"❌ Ошибка авторизации: {str(e)}", None
    
    def complete_auth(self, auth_code: str) -> Tuple[bool, str]:
        """Завершает авторизацию с кодом"""
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            
            SCOPES = ['https://www.googleapis.com/auth/drive.file']
            
            flow = InstalledAppFlow.from_client_secrets_file(
                self.credentials_path,
                SCOPES,
                redirect_uri='urn:ietf:wg:oauth:2.0:oob'
            )
            
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            
            self._save_token(creds)
            self.service = self._build_service(creds)
            self.authenticated = True
            
            return True, "✅ Авторизация успешна"
            
        except Exception as e:
            return False, f"❌ Ошибка: {str(e)}"
    
    def sync(self, local_path: str, filename: str = 'taxi_backup.db') -> Tuple[bool, str, str]:
        """
        Синхронизация файла с Google Drive
        Возвращает: (успех, сообщение, направление)
        """
        if not self.authenticated:
            return False, "❌ Не авторизовано", ""
        
        try:
            from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
            import io
            
            # Ищем файл в Drive
            query = f"name='{filename}' and trashed=false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, modifiedTime)'
            ).execute()
            
            files = results.get('files', [])
            local_mtime = datetime.fromtimestamp(os.path.getmtime(local_path))
            
            if not files:
                # Файла нет в облаке → загружаем
                return self._upload_file(local_path, filename)
            else:
                # Файл есть → сравниваем время
                cloud_mtime = datetime.fromisoformat(
                    files[0]['modifiedTime'].replace('Z', '+00:00')
                )
                
                if local_mtime > cloud_mtime:
                    return self._upload_file(local_path, filename, files[0]['id'])
                else:
                    return self._download_file(files[0]['id'], local_path)
                    
        except Exception as e:
            return False, f"❌ Ошибка синхронизации: {str(e)}", ""
    
    def _upload_file(self, local_path: str, filename: str, file_id: str = None) -> Tuple[bool, str, str]:
        """Загрузка файла в Drive"""
        from googleapiclient.http import MediaFileUpload
        
        try:
            media = MediaFileUpload(local_path, mimetype='application/octet-stream')
            
            if file_id:
                self.service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
            else:
                file_metadata = {'name': filename}
                self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
            
            return True, "✅ Загружено в Google Drive", "upload"
            
        except Exception as e:
            return False, f"❌ Ошибка загрузки: {str(e)}", ""
    
    def _download_file(self, file_id: str, local_path: str) -> Tuple[bool, str, str]:
        """Скачивание файла из Drive"""
        from googleapiclient.http import MediaIoBaseDownload
        
        try:
            request = self.service.files().get_media(fileId=file_id)
            
            temp_path = local_path + ".temp"
            with open(temp_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
            
            import shutil
            shutil.copy2(temp_path, local_path)
            os.remove(temp_path)
            
            return True, "✅ Скачано из Google Drive", "download"
            
        except Exception as e:
            return False, f"❌ Ошибка скачивания: {str(e)}", ""
    
    def _build_service(self, creds):
        """Создаёт сервис Google Drive"""
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        
        return build('drive', 'v3', credentials=creds)
    
    def _get_request(self):
        """Создаёт Request объект для обновления токена"""
        from google.auth.transport.requests import Request
        return Request()
    
    def _save_token(self, creds):
        """Сохраняет токен"""
        with open(self.token_path, 'w') as token:
            token.write(creds.to_json())
    
    def get_sync_status(self) -> dict:
        """Возвращает статус синхронизации"""
        return {
            'authenticated': self.authenticated,
            'credentials_exists': os.path.exists(self.credentials_path),
            'token_exists': os.path.exists(self.token_path),
        }