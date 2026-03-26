# fix_credentials.py
import json

with open("credentials.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Очищаем все строковые значения от пробелов
def clean(obj):
    if isinstance(obj, dict):
        return {k.strip(): clean(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean(item) for item in obj]
    elif isinstance(obj, str):
        return obj.strip()
    return obj

cleaned = clean(data)

with open("credentials.json", "w", encoding="utf-8") as f:
    json.dump(cleaned, f, ensure_ascii=False, indent=2)

print("✅ credentials.json очищен!")