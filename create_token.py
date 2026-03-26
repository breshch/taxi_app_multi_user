from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CODE = "4/0Aci98E--Gu4uNlhmBRLhwUWWiWYiN2e1MJyJES0T06V_LjF2KF1rxwiLJ4EZPDa4SOygtw"

# Создаём flow
flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES,
    redirect_uri="http://localhost:8501"  # Для локальной отладки
)

# Получаем токен
flow.fetch_token(code=CODE)
creds = flow.credentials

# Сохраняем
with open("token.json", "w", encoding="utf-8") as f:
    f.write(creds.to_json())

print("✅ token.json создан!")
print(f"Access token: {creds.token[:50]}...")
print(f"Refresh token: {creds.refresh_token[:50] if creds.refresh_token else 'None'}...")