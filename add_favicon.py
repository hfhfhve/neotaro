#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_favicon.py — добавляет блок иконок во ВСЕ .html файлы сайта neotaro.ru.

Запуск из корня репозитория:
    python3 add_favicon.py --dry-run     # показать, что будет сделано (ничего не меняет)
    python3 add_favicon.py               # применить изменения
    python3 add_favicon.py --force       # переписать блок даже там, где он уже есть

Скрипт идемпотентный: повторный запуск ничего не ломает и не плодит дубли.
"""

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- настройки

MARKER = "<!-- neotaro-icons -->"

# Единый блок иконок. Правь только здесь — применится ко всем страницам.
ICON_BLOCK = """<!-- neotaro-icons -->
<link rel="icon" type="image/png" href="/favicon-96x96.png" sizes="96x96">
<link rel="icon" type="image/png" href="/favicon-192x192.png" sizes="192x192">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="shortcut icon" href="/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<!-- /neotaro-icons -->"""

# Папки, которые не трогаем
SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "assets"}

# ---------------------------------------------------------------- регулярки

# Уже вставленный нами блок (для --force и для очистки)
RE_OUR_BLOCK = re.compile(
    re.escape(MARKER) + r".*?<!--\s*/neotaro-icons\s*-->\s*",
    re.DOTALL | re.IGNORECASE,
)

# Любые «иконочные» link-теги, которые могли быть раньше
RE_OLD_ICON_LINKS = re.compile(
    r"[ \t]*<link\b[^>]*\brel\s*=\s*[\"']\s*(?:shortcut\s+icon|icon|apple-touch-icon|apple-touch-icon-precomposed|mask-icon|manifest)\s*[\"'][^>]*>\s*\n?",
    re.IGNORECASE,
)

RE_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
RE_CHARSET = re.compile(r"<meta\b[^>]*charset[^>]*>", re.IGNORECASE)
RE_VIEWPORT = re.compile(r"<meta\b[^>]*name\s*=\s*[\"']viewport[\"'][^>]*>", re.IGNORECASE)

# ---------------------------------------------------------------- обработка


def process(html: str, force: bool):
    """Возвращает (новый_html, статус)."""

    if MARKER in html and not force:
        return html, "skip_has_marker"

    if not RE_HEAD_OPEN.search(html):
        return html, "error_no_head"

    # 1. Убираем наш старый блок (если --force)
    html = RE_OUR_BLOCK.sub("", html)

    # 2. Убираем все прежние иконочные link-теги, чтобы не было дублей
    html, removed = RE_OLD_ICON_LINKS.subn("", html)

    # 3. Ищем точку вставки: после viewport, иначе после charset, иначе после <head>
    anchor = None
    for rx in (RE_VIEWPORT, RE_CHARSET, RE_HEAD_OPEN):
        m = rx.search(html)
        if m:
            anchor = m
            break

    pos = anchor.end()
    html = html[:pos] + "\n" + ICON_BLOCK + html[pos:]

    return html, ("rewritten" if removed else "added")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".", help="корень сайта (по умолчанию текущая папка)")
    ap.add_argument("--dry-run", action="store_true", help="только показать, не менять файлы")
    ap.add_argument("--force", action="store_true", help="переписать блок даже если он уже есть")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"Нет такой папки: {root}")

    files = [
        p
        for p in root.rglob("*.html")
        if not SKIP_DIRS & set(p.relative_to(root).parts)
    ]

    stats = {"added": 0, "rewritten": 0, "skip_has_marker": 0, "error_no_head": 0}
    changed, problems = [], []

    for path in sorted(files):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append((path, "не UTF-8"))
            continue

        new, status = process(original, args.force)
        stats[status] = stats.get(status, 0) + 1

        if status == "error_no_head":
            problems.append((path, "нет тега <head>"))
            continue

        if new != original:
            changed.append(path)
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")

    # ------------------------------------------------------------ отчёт
    mode = "ПРЕДПРОСМОТР (файлы не изменены)" if args.dry_run else "ПРИМЕНЕНО"
    print(f"=== {mode} ===")
    print(f"Корень:            {root}")
    print(f"Всего .html:       {len(files)}")
    print(f"Добавлен блок:     {stats['added']}")
    print(f"Переписан блок:    {stats['rewritten']}")
    print(f"Уже было, пропуск: {stats['skip_has_marker']}")
    print(f"Изменено файлов:   {len(changed)}")

    if changed:
        print("\nПервые 15 изменённых:")
        for p in changed[:15]:
            print("  ", p.relative_to(root))
        if len(changed) > 15:
            print(f"   ... и ещё {len(changed) - 15}")

    if problems:
        print(f"\n!!! Проблемные файлы ({len(problems)}):")
        for p, why in problems[:20]:
            print(f"   {p.relative_to(root)} — {why}")


if __name__ == "__main__":
    main()
