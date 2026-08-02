#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_sitemap.py - генератор sitemap.xml для статического сайта на GitHub Pages.

Запуск из корня репозитория фронтенда:
    python3 gen_sitemap.py

Обходит все .html, собирает URL, пропускает служебное и всё,
где в коде стоит noindex. lastmod берётся из git, иначе из mtime файла.
"""

import os
import re
import subprocess
import datetime
from xml.sax.saxutils import escape

# ---------- НАСТРОЙКИ ----------

SITE = "https://neotaro.ru"
ROOT = "."
OUT = "sitemap.xml"

# Папки, которые не попадают в поиск
SKIP_DIRS = {
    ".git", ".github", "node_modules", "assets", "static",
    "css", "js", "img", "images", "fonts", "app", "login",
}

# Отдельные файлы, которые не нужны в sitemap
SKIP_FILES = {"404.html", "google", "yandex"}

# Приоритеты по глубине вложенности
PRIORITY = {0: "1.0", 1: "0.8", 2: "0.6"}
DEFAULT_PRIORITY = "0.5"

NOINDEX = re.compile(r'name=["\']robots["\'][^>]*noindex', re.I)


def git_lastmod(path):
    """Дата последнего коммита файла, если это git-репозиторий."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", path],
            capture_output=True, text=True, timeout=10,
        )
        v = out.stdout.strip()
        if v:
            return v[:10]
    except Exception:
        pass
    return None


def mtime_lastmod(path):
    ts = os.path.getmtime(path)
    return datetime.date.fromtimestamp(ts).isoformat()


def to_url(relpath):
    """Путь файла -> канонический URL со слешем на конце."""
    p = relpath.replace(os.sep, "/")
    if p == "index.html":
        return SITE + "/"
    if p.endswith("/index.html"):
        return SITE + "/" + p[: -len("index.html")]
    # одиночный page.html -> /page/  (GitHub Pages отдаёт и так, и так)
    return SITE + "/" + p[: -len(".html")] + "/"


def main():
    entries = []
    skipped_noindex = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            if fn in SKIP_FILES:
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, ROOT)

            try:
                with open(full, "r", encoding="utf-8", errors="ignore") as f:
                    head = f.read(4000)
            except Exception:
                head = ""
            if NOINDEX.search(head):
                skipped_noindex += 1
                continue

            url = to_url(rel)
            depth = url[len(SITE):].strip("/").count("/") if url != SITE + "/" else 0
            if url == SITE + "/":
                depth = 0
            else:
                depth = len([s for s in url[len(SITE):].strip("/").split("/") if s])

            entries.append({
                "loc": url,
                "lastmod": git_lastmod(rel) or mtime_lastmod(full),
                "priority": PRIORITY.get(depth, DEFAULT_PRIORITY),
            })

    # убираем дубли, сортируем
    seen = {}
    for e in entries:
        seen[e["loc"]] = e
    entries = sorted(seen.values(), key=lambda e: e["loc"])

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for e in entries:
        lines.append("  <url>")
        lines.append("    <loc>%s</loc>" % escape(e["loc"]))
        lines.append("    <lastmod>%s</lastmod>" % e["lastmod"])
        lines.append("    <priority>%s</priority>" % e["priority"])
        lines.append("  </url>")
    lines.append("</urlset>")

    data = "\n".join(lines) + "\n"
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(data)

    print("Страниц в sitemap: %d" % len(entries))
    print("Пропущено по noindex: %d" % skipped_noindex)
    print("Размер файла: %.1f КБ" % (len(data.encode("utf-8")) / 1024))
    print("Записано: %s" % os.path.abspath(OUT))
    if entries:
        print("\nПервые 5:")
        for e in entries[:5]:
            print("  " + e["loc"])


if __name__ == "__main__":
    main()
