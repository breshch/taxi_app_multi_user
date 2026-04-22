#!/usr/bin/env python3
# analyze.py — статический анализатор (только корневые .py файлы проекта)
import os, ast, sys

EXCLUDE_DIRS = {
    ".git", "venv", "venv311", ".venv", ".venv-1", ".venv-2",
    "__pycache__", ".idea", ".vscode", "node_modules",
    "site-packages", "dist-packages", "dist-info", "Lib", "Scripts",
}
EXCLUDE_FILES = {"analyze.py"}
MAX_FILE_SIZE = 500_000  # байт — пропускаем файлы > 500 KB

def collect_py_files(path):
    files = []
    # Только файлы ПРЯМО в корне папки, без рекурсии в подпапки venv
    for entry in os.scandir(path):
        if entry.is_file() and entry.name.endswith(".py") and entry.name not in EXCLUDE_FILES:
            files.append(entry.path)
        elif entry.is_dir():
            name = entry.name
            if name in EXCLUDE_DIRS or name.startswith("venv") or name.startswith(".venv"):
                continue
            # Один уровень вложенности (папка pages, utils и т.п.)
            try:
                for sub in os.scandir(entry.path):
                    if sub.is_file() and sub.name.endswith(".py") and sub.name not in EXCLUDE_FILES:
                        files.append(sub.path)
            except PermissionError:
                pass
    return sorted(files)

def analyze_file(filepath):
    try:
        size = os.path.getsize(filepath)
        if size > MAX_FILE_SIZE:
            return {"error": f"файл слишком большой ({size//1024} KB), пропущен", "functions": [], "imports": [], "issues": [], "lines": 0}
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            source = f.read()
    except Exception as e:
        return {"error": str(e), "functions": [], "imports": [], "issues": [], "lines": 0}

    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}", "functions": [], "imports": [], "issues": [], "lines": len(lines)}

    functions, imports = [], []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            imports.append(f"from {node.module} import ...")

    issues = []
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if "use_container_width" in s:
            issues.append(f"  ⚠️  строка {i}: устаревший `use_container_width` → замени на `width=`")
        if s == "except:":
            issues.append(f"  ⚠️  строка {i}: голый except — лучше except Exception as e:")
        if "st.experimental_" in s:
            issues.append(f"  ⚠️  строка {i}: st.experimental_* устарел")
        if ("TODO" in s or "FIXME" in s) and not s.startswith("#"):
            issues.append(f"  📝  строка {i}: {s[:80]}")

    return {"functions": functions, "imports": list(dict.fromkeys(imports)), "issues": issues, "lines": len(lines), "error": None}

def run(path="."):
    files = collect_py_files(path)
    if not files:
        print("Файлы не найдены.")
        return

    total_issues = total_functions = total_lines = 0
    print(f"\n{'='*60}")
    print(f"  АНАЛИЗ: {os.path.abspath(path)}")
    print(f"  Файлов: {len(files)}")
    print(f"{'='*60}\n")

    for fp in files:
        rel = os.path.relpath(fp, path)
        r = analyze_file(fp)
        total_lines += r["lines"]; total_functions += len(r["functions"]); total_issues += len(r["issues"])
        if r["error"]:
            print(f"📄 {rel}  — ❌ {r['error']}")
        else:
            flist = ", ".join(r["functions"][:10]) + (f" ... (+{len(r['functions'])-10})" if len(r["functions"])>10 else "")
            print(f"📄 {rel}  — ✅ {r['lines']} строк | {len(r['functions'])} функций")
            if flist: print(f"   Функции: {flist}")
            if r["imports"]:
                ilist = ", ".join(r["imports"][:8]) + (f" ... (+{len(r['imports'])-8})" if len(r["imports"])>8 else "")
                print(f"   Импорты: {ilist}")
        for iss in r["issues"]:
            print(iss)
        print()

    print(f"{'='*60}")
    print(f"  ИТОГО: {len(files)} файлов | {total_lines} строк | {total_functions} функций | {total_issues} замечаний")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else ".")
