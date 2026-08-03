#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_indexnow_list.py

Собирает список URL для отправки в IndexNow и кладёт его в urls.json.

Переменные окружения:
  HOST        - домен без схемы, например neotaro.ru
  KEY         - ключ IndexNow
  SUBMIT_ALL  - "true" -> все страницы; иначе только изменённые в последнем коммите
"""

import json
import os
import subprocess
from pathlib import Path

HOST = os.environ.get("HOST", "neotaro.ru")
KEY = os.environ.get("KEY", "")
SUBMIT_ALL = os.environ.get("SUBMIT_ALL", "").lower() == "true"

BASE = "https://" + HOST

# IndexNow принимает максимум 10 000 URL за запрос
MAX_URLS = 10000

SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "assets"}
# Служебные страницы, которые в индекс отправлять не надо
SKIP_FILES = {"404.html", "diag.html"}

root = Path(".").resolve()


def to_url(rel):
    """Путь в репо -> канонический URL сайта. Возвращает None, если пропуск."""
    rel = rel.strip()
    while rel.startswith("./"):
        rel = rel[2:]
    rel = rel.lstrip("/")

    if not rel.endswith(".html"):
        return None

    parts = rel.split("/")
    if SKIP_DIRS.intersection(parts):
        return None
    if parts[-1] in SKIP_FILES:
        return None

    if parts[-1] == "index.html":
        folder = "/".join(parts[:-1])
        if folder:
            return BASE + "/" + folder + "/"
        return BASE + "/"

    return BASE + "/" + rel


def changed_files():
    """HTML-файлы, изменённые в последнем коммите."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRT", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    return [line for line in out.splitlines() if line.endswith(".html")]


if SUBMIT_ALL:
    files = [
        str(p.relative_to(root))
        for p in root.rglob("*.html")
        if not SKIP_DIRS.intersection(p.relative_to(root).parts)
    ]
    mode = "ВСЕ страницы"
else:
    files = changed_files()
    mode = "только изменённые"

urls = set()
for f in files:
    u = to_url(f)
    if u:
        urls.add(u)
urls = sorted(urls)

if len(urls) > MAX_URLS:
    print("URL больше " + str(MAX_URLS) + ", обрезаю.")
    urls = urls[:MAX_URLS]

print("Режим: " + mode)
print("HTML-файлов найдено: " + str(len(files)))
print("URL к отправке:      " + str(len(urls)))
for u in urls[:20]:
    print("   ", u)
if len(urls) > 20:
    print("    ... и ещё " + str(len(urls) - 20))

if not urls:
    Path("urls.json").write_text("", encoding="utf-8")
    raise SystemExit(0)

payload = {
    "host": HOST,
    "key": KEY,
    "keyLocation": BASE + "/" + KEY + ".txt",
    "urlList": urls,
}

Path("urls.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
print("urls.json готов.")
