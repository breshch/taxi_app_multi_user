#!/usr/bin/env python3
"""
fix_ucw.py — заменяет устаревший use_container_width на width=
Использование: python fix_ucw.py app.py [другие файлы...]
"""
import sys, re, shutil, py_compile, tempfile, os
from pathlib import Path

def fix_file(path: str) -> int:
    p = Path(path)
    if not p.exists():
        print(f"[SKIP] не найден: {path}")
        return 0

    src = p.read_text(encoding="utf-8")
    new = src.replace("use_container_width=True",  "width='stretch'")
    new = new.replace("use_container_width=False", "width='content'")

    count = src.count("use_container_width=True") + src.count("use_container_width=False")
    if count == 0:
        print(f"[OK] {path} — нет устаревших вхождений")
        return 0

    # Проверяем синтаксис
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False,
                                     mode="w", encoding="utf-8") as tf:
        tf.write(new); tname = tf.name
    try:
        py_compile.compile(tname, doraise=True)
    except py_compile.PyCompileError as e:
        print(f"[ERR] синтаксис после замены: {e}")
        return 0
    finally:
        os.unlink(tname)

    # Бэкап оригинала
    backup = str(p) + ".bak"
    shutil.copy2(p, backup)

    p.write_text(new, encoding="utf-8")
    print(f"[FIXED] {path} — {count} замен. Оригинал → {backup}")
    return count

if __name__ == "__main__":
    files = sys.argv[1:] or ["app.py"]
    total = 0
    for f in files:
        total += fix_file(f)
    print(f"\nИтого замен: {total}")
