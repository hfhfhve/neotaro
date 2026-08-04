#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fix_mail.py — меняет личный gmail на support@neotaro.ru во всех файлах сайта.

Зачем: личный адрес в разметке Organization — это и несолидно для посетителя,
и минус для поисковиков: корпоративная почта на своём домене — один из сигналов
реальности организации.

Запуск из корня репозитория:
    python3 fix_mail.py --dry-run
    python3 fix_mail.py

Заменяет ЛЮБОЙ адрес вида timurrahimzyanov<цифры>@gmail.com — чтобы не зависеть
от того, где 10, а где 11. Работает и в mailto:, и в видимом тексте, и в JSON-LD.
После успешного прогона скрипт и его workflow можно удалить — он одноразовый.
"""

import argparse
import re
import sys
from pathlib import Path

NEW_MAIL = "support@neotaro.ru"

# Любой личный адрес автора, с любыми цифрами в конце.
RE_MAIL = re.compile(r"timurrahimzyanov\d*@gmail\.com", re.I)

# Расширения, в которых адрес может встретиться.
EXTS = {".html", ".htm", ".xml", ".json", ".webmanifest", ".txt", ".md"}

SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "assets"}


def walk(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if p.suffix.lower() not in EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        yield p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".", help="корень сайта")
    ap.add_argument("--dry-run", action="store_true", help="только показать")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"Нет такой папки: {root}")

    mode = "ПРЕДПРОСМОТР (файлы не изменены)" if args.dry_run else "ПРИМЕНЕНО"
    print(f"=== {mode} ===")
    print(f"Корень:       {root}")
    print(f"Новый адрес: {NEW_MAIL}")

    files_seen = 0
    files_hit = 0
    total_repl = 0
    changed = []
    per_variant = {}

    for path in walk(root):
        files_seen += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        found = RE_MAIL.findall(text)
        if not found:
            continue

        for f in found:
            per_variant[f.lower()] = per_variant.get(f.lower(), 0) + 1

        new_text = RE_MAIL.sub(NEW_MAIL, text)
        files_hit += 1
        total_repl += len(found)
        changed.append((str(path.relative_to(root)), len(found)))

        if not args.dry_run:
            path.write_text(new_text, encoding="utf-8")

    print(f"\nПросмотрено файлов: {files_seen}")
    print(f"С адресом:          {files_hit}")
    print(f"Всего замен:       {total_repl}")

    if per_variant:
        print("\nЧто именно встретилось:")
        for k, v in sorted(per_variant.items()):
            print(f"   {k}: {v}")

    if changed:
        print("\nПервые 15 файлов:")
        for rel, n in changed[:15]:
            print(f"   {rel}  ({n})")
        if len(changed) > 15:
            print(f"   ... и ещё {len(changed) - 15}")
    else:
        print("\nНи одного вхождения не найдено — менять нечего.")


if __name__ == "__main__":
    main()
