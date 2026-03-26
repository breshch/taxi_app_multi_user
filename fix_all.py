import json
import re

def fix_credentials():
    """Исправляет credentials.json"""
    with open("credentials.json", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Парсим и очищаем
    data = json.loads(content)
    
    # Рекурсивно очищаем все строки от пробелов
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
    
    print("✅ credentials.json исправлен")

def fix_python_file(filename):
    """Исправляет Python файл"""
    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Список всех замен
    replacements = [
        ("Req uest()", "Request()"),
        ("nex t_chunk()", "next_chunk()"),
        ("loc al_path", "local_path"),
        ("InstalledAppF low", "InstalledAppFlow"),
        ("tips _f", "tips_f"),
        ("e_fina l", "e_final"),
        ("tota l_extra", "total_extra"),
        ("year _months", "year_months"),
        ("get_month_st atistics", "get_month_statistics"),
        ("if name == \"main\"", "if __name__ == \"__main__\""),
        ("f \"{", "f\"{"),
    ]
    
    for old, new in replacements:
        content = content.replace(old, new)
    
    # Удаляем пробелы в конце строк в кавычках
    content = re.sub(r'"([^"]*?)\s+"', r'"\1"', content)
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"✅ {filename} исправлен")

if __name__ == "__main__":
    fix_credentials()
    fix_python_file("app.py")
    fix_python_file("pages_imports.py")
    fix_python_file("config.py")
    print("\n🎉 Все файлы исправлены!")