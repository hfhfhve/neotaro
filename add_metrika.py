#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_metrika.py — добавляет счётчик Яндекс.Метрики во ВСЕ .html файлы neotaro.ru.

Запуск из корня репозитория:
    python3 add_metrika.py --id 98765432 --dry-run   # показать, ничего не меняя
    python3 add_metrika.py --id 98765432             # применить
    python3 add_metrika.py --id 98765432 --force     # переписать даже там, где блок уже есть

Номер счётчика можно задать и переменной окружения METRIKA_ID — так удобнее в GitHub Actions.

Скрипт идемпотентный: повторный запуск ничего не ломает и не плодит второй счётчик.
Два счётчика на одной странице — это двойные визиты и сломанная статистика, поэтому
чужие вставки mc.yandex.ru тоже вырезаются.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- настройки

MARKER = "<!-- neotaro-metrika -->"

# Папки, которые не трогаем
SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "assets"}

# Служебные страницы: считать их визиты смысла нет, только шум в отчётах
SKIP_FILES = {"diag.html"}


def build_block(counter_id: str) -> str:
    """Собирает блок счётчика. Правь только здесь — применится ко всем страницам."""
    return f"""<!-- neotaro-metrika -->
<script type="text/javascript">
   (function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
   m[i].l=1*new Date();
   for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}})
   (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

   ym({counter_id}, "init", {{
        clickmap: true,
        trackLinks: true,
        accurateTrackBounce: true,
        webvisor: true
   }});

   /* Единая точка для целей. Везде в коде зовём neoGoal('register'),
      а не ym(...) напрямую: номер счётчика остаётся в одном месте,
      и при блокировщике рекламы страница не падает с ошибкой. */
   window.NEO_METRIKA_ID = {counter_id};
   window.neoGoal = function(name, params){{
     try {{ if (typeof ym === 'function') ym({counter_id}, 'reachGoal', name, params || {{}}); }} catch(e){{}}
   }};
   window.neoHit = function(url, options){{
     try {{ if (typeof ym === 'function') ym({counter_id}, 'hit', url, options || {{}}); }} catch(e){{}}
   }};
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/{counter_id}" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /neotaro-metrika -->"""


# ---------------------------------------------------------------- регулярки

# Наш собственный блок (для --force и для очистки)
RE_OUR_BLOCK = re.compile(
    re.escape(MARKER) + r".*?<!--\s*/neotaro-metrika\s*-->\s*",
    re.DOTALL | re.IGNORECASE,
)

# Чужие/ручные вставки Метрики: <script>...mc.yandex.ru...</script>
RE_OLD_METRIKA_SCRIPT = re.compile(
    r"[ \t]*<script\b[^>]*>(?:(?!</script>).)*?mc\.yandex\.ru(?:(?!</script>).)*?</script>\s*\n?",
    re.DOTALL | re.IGNORECASE,
)

# Сопутствующий <noscript> с пикселем
RE_OLD_METRIKA_NOSCRIPT = re.compile(
    r"[ \t]*<noscript>(?:(?!</noscript>).)*?mc\.yandex\.ru(?:(?!</noscript>).)*?</noscript>\s*\n?",
    re.DOTALL | re.IGNORECASE,
)

RE_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
RE_CHARSET = re.compile(r"<meta\b[^>]*charset[^>]*>", re.IGNORECASE)
RE_VIEWPORT = re.compile(r"<meta\b[^>]*name\s*=\s*[\"']viewport[\"'][^>]*>", re.IGNORECASE)

# ---------------------------------------------------------------- обработка


def process(html: str, block: str, force: bool):
    """Возвращает (новый_html, статус)."""

    if MARKER in html and not force:
        return html, "skip_has_marker"

    if not RE_HEAD_OPEN.search(html):
        return html, "error_no_head"

    # 1. Убираем наш старый блок (если --force)
    html = RE_OUR_BLOCK.sub("", html)

    # 2. Убираем любые прежние счётчики, чтобы не считать визиты дважды
    html, n1 = RE_OLD_METRIKA_SCRIPT.subn("", html)
    html, n2 = RE_OLD_METRIKA_NOSCRIPT.subn("", html)
    removed = n1 + n2

    # 3. Точка вставки: после viewport, иначе после charset, иначе сразу за <head>.
    #    Метрика хочет быть как можно выше в <head>, иначе теряются быстрые уходы.
    anchor = None
    for rx in (RE_VIEWPORT, RE_CHARSET, RE_HEAD_OPEN):
        m = rx.search(html)
        if m:
            anchor = m
            break

    pos = anchor.end()
    html = html[:pos] + "\n" + block + html[pos:]

    return html, ("rewritten" if removed else "added")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".", help="корень сайта (по умолчанию текущая папка)")
    ap.add_argument("--id", dest="counter_id", default=os.getenv("METRIKA_ID", ""),
                    help="номер счётчика Метрики (или переменная METRIKA_ID)")
    ap.add_argument("--dry-run", action="store_true", help="только показать, не менять файлы")
    ap.add_argument("--force", action="store_true", help="переписать блок даже если он уже есть")
    args = ap.parse_args()

    counter_id = str(args.counter_id).strip()
    if not counter_id.isdigit():
        sys.exit(
            "Нужен номер счётчика Метрики (только цифры).\n"
            "  Где взять: metrika.yandex.ru → счётчик → номер вверху, вида 98765432\n"
            "  Как передать: python3 add_metrika.py --id 98765432\n"
            "            или METRIKA_ID=98765432 python3 add_metrika.py"
        )

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"Нет такой папки: {root}")

    block = build_block(counter_id)

    files = [
        p
        for p in root.rglob("*.html")
        if not SKIP_DIRS & set(p.relative_to(root).parts)
        and p.name not in SKIP_FILES
    ]

    stats = {"added": 0, "rewritten": 0, "skip_has_marker": 0, "error_no_head": 0}
    changed, problems = [], []

    for path in sorted(files):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append((path, "не UTF-8"))
            continue

        new, status = process(original, block, args.force)
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
    print(f"Счётчик:           {counter_id}")
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
