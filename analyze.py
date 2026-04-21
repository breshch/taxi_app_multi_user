import os
import ollama

def analyze_project(path):
    all_code = ""
    # Папки, которые не нужно читать
    exclude_dirs = {'.git', 'venv', '__pycache__', '.idea', '.vscode'}
    
    for root, dirs, files in os.walk(path):
        # Удаляем ненужные папки из обхода
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    # Добавляем encoding='utf-8' и errors='ignore'
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        all_code += f"\n--- File: {file} ---\n" + f.read()
                except Exception as e:
                    print(f"Не удалось прочитать {file}: {e}")

    if not all_code:
        print("Код не найден!")
        return

    print("Анализирую проект...")
    response = ollama.generate(
        model='py-reviewer',
        prompt=f"Проанализируй весь этот Python проект и найди ошибки:\n\n{all_code}"
    )
    print(response['response'])

analyze_project('.') 
