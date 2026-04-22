#!/usr/bin/env python3
"""
cleanup_local.py — удаляет лишние файлы в папке проекта
Запуск: python cleanup_local.py [папка]  (по умолчанию — текущая)
"""
import os, sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

# Паттерны лишних файлов
REMOVE_PATTERNS = [
    "app.py.bak*",
    "app.py.bak_*",
    "*.bak",
    "patch_*.py",
    "cleanup*.py",
    "fix_bare_except.py",
    "google_drive_debug.log",
    "logs-breshch-*.txt",
    "forecast_preview.html",
    "app_v*.py",
    "app_final.py",
    "app_nocharts.py",
    "app_forecast*.py",
    "app_ucw_fixed.py",
    "__pycache__",
]

# Файлы которые НЕЛЬЗЯ трогать
KEEP = {
    "app.py", "config.py", "requirements.txt",
    "credentials.json", "session.json", "packages.txt",
    "analyze.py", "fix_all.py", "fix_credentials.py",
    "pages_imports.py", "create_token.py", "fix_ucw.py",
    "cleanup_local.py",
}

deleted = []
skipped = []

for pattern in REMOVE_PATTERNS:
    for path in ROOT.glob(pattern):
        if path.name in KEEP:
            skipped.append(path.name)
            continue
        try:
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            else:
                path.unlink()
            deleted.append(str(path))
        except Exception as e:
            print(f"[ERR] {path}: {e}")

print(f"\n✅ Удалено {len(deleted)} файлов:")
for f in deleted:
    print(f"  🗑 {f}")

if skipped:
    print(f"\n⚠️  Пропущено (в списке KEEP): {skipped}")

if not deleted:
    print("  Лишних файлов не найдено — всё чисто!")
