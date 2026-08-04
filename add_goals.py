#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_goals.py — расставляет цели Яндекс.Метрики в лендинге и в кабинете.

Запуск из корня репозитория:
    python3 add_goals.py --dry-run     # показать, ничего не меняя
    python3 add_goals.py               # применить

Скрипт идемпотентный: каждая вставка помечена комментарием /* neotaro-goal */
и перед работой проверяется на наличие. Повторный запуск ничего не дублирует.

Важно: каждый якорь обязан встретиться РОВНО ОДИН раз. Если не так — скрипт
падает и не трогает файл. Лучше сломаться в Actions, чем тихо испортить живой файл.
"""

import argparse
import sys
from pathlib import Path

MARK = "/* neotaro-goal */"

# Какие файлы правим.
LANDING = "index.html"          # лендинг в корне сайта
APP = "app/index.html"          # кабинет

# ------------------------------------------------------------------ вставки
#
# where: "before" — перед якорем, "after" — сразу после него.
#
EDITS = [
    # ---------------------------------------------------------- лендинг
    {
        "file": LANDING,
        "name": "yesno_widget — человек отправил вопрос",
        "where": "before",
        "anchor": "    busy = true;\n"
                  "    go.disabled = true;\n"
                  "    label.textContent = 'Карты тасуются…';",
        "insert": "    if(window.neoGoal) neoGoal('yesno_widget'); " + MARK + "\n",
    },
    {
        "file": LANDING,
        "name": "yesno_done — расклад показан",
        "where": "before",
        "anchor": "      try { out.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch(e){}",
        "insert": "      if(window.neoGoal) neoGoal('yesno_done', { verdict: data.verdict || '' }); " + MARK + "\n",
    },
    {
        "file": LANDING,
        "name": "yesno_limit — бесплатные вопросы закончились",
        "where": "after",
        "anchor": "          tEl.innerHTML = 'Бесплатные вопросы на сегодня закончились. В кабинете ограничений нет.';",
        "insert": "\n          if(window.neoGoal) neoGoal('yesno_limit'); " + MARK,
    },
    {
        "file": LANDING,
        "name": "login_click — клик по любой кнопке, ведущей на /login/",
        "where": "before",
        "anchor": "</body>",
        "insert": """<script>
/* neotaro-goal — один обработчик на все ссылки входа вместо шести отдельных правок. */
(function(){
  document.addEventListener('click', function(e){
    var t = e.target;
    if(!t || !t.closest) return;
    var a = t.closest('a[href*="/login/"]');
    if(!a) return;
    var href = a.getAttribute('href') || '';
    var place = 'cta';
    if(a.id === 'yn-lock-btn') place = 'yesno_lock';
    else if(href.indexOf('mode=login') !== -1) place = 'have_account';
    else if(a.className && String(a.className).indexOf('lp-top-cta') !== -1) place = 'header';
    if(window.neoGoal) neoGoal('login_click', { place: place });
  }, true);
})();
</script>
""",
    },

    # ---------------------------------------------------------- кабинет
    {
        "file": APP,
        "name": "виртуальные просмотры при смене экрана",
        "where": "before",
        "anchor": "  if(LOADERS[view]) LOADERS[view]();\n  bridge.haptic();\n}",
        "insert": "  if(window.neoHit) neoHit('/app/#' + view, { title: 'app: ' + view }); " + MARK + "\n",
    },
    {
        "file": APP,
        "name": "spread_done и first_spread — расклад готов",
        "where": "after",
        "anchor": "    out.innerHTML = clean(data.interpretation || '');\n"
                  "    if(typeof data.energy === 'number'){ S.energy = data.energy; paintEnergy(); }\n"
                  "    bridge.haptic('ok');",
        "insert": """
    if(window.neoGoal){ /* neotaro-goal */
      neoGoal('spread_done', { spread: (S.spread && S.spread.id) || '' });
      /* Первый расклад отмечаем ровно один раз — это активация, а не повторное действие. */
      try{
        if(!localStorage.getItem('neo_first_spread')){
          localStorage.setItem('neo_first_spread', '1');
          neoGoal('first_spread');
        }
      }catch(e){}
    }""",
    },
    {
        "file": APP,
        "name": "paywall_view — открыта шторка подписки",
        "where": "after",
        "anchor": "  if(id === 'sub'){\n    renderSubSheet();",
        "insert": "\n    if(window.neoGoal) neoGoal('paywall_view', { place: 'sub_sheet' }); " + MARK,
    },
    {
        "file": APP,
        "name": "paywall_view — показан пейволл в натальной карте",
        "where": "after",
        "anchor": "  document.getElementById('as-paywall').style.display = paid ? 'none' : 'block';",
        "insert": "\n  if(!paid && window.neoGoal) neoGoal('paywall_view', { place: 'astro' }); " + MARK,
    },
    {
        "file": APP,
        "name": "purchase_start — создан счёт на подписку",
        "where": "before",
        "anchor": "  const d = await api('/subscription/invoice-rub', 'POST', { plan: plan, period: S.per });",
        "insert": "  if(window.neoGoal) neoGoal('purchase_start', { kind: 'subscription', plan: plan, period: S.per }); " + MARK + "\n",
    },
    {
        "file": APP,
        "name": "purchase — оплата подтверждена",
        "where": "after",
        "anchor": "      hideToast();\n      toast(tt('pay_done'));\n      bridge.haptic('ok');",
        "insert": "\n      if(window.neoGoal) neoGoal('purchase'); " + MARK,
    },
    {
        "file": APP,
        "name": "signin — вход через код Telegram",
        "where": "before",
        "anchor": "      bridge.token = res.token;\n"
                  "      bridge.webUser = res.user || null;\n"
                  "      boot();",
        "insert": "      if(window.neoGoal) neoGoal('signin', { method: 'telegram_code' }); " + MARK + "\n",
    },
]


# ------------------------------------------------------------------ логика


def _probe(snippet: str) -> str:
    """Строка-отпечаток, по которой понятно, что вставка уже сделана.

    Берём самую длинную строку с вызовом цели — она уникальна.
    Первая строка не годится: у блока с обработчиком кликов это '<script>',
    который есть в любом файле, и вставка ложно считалась бы сделанной.
    """
    cands = [l.strip() for l in snippet.split("\n") if "neoGoal(" in l or "neoHit(" in l]
    if cands:
        return max(cands, key=len)
    return snippet.strip().split("\n")[0].strip()


def apply_edits(root: Path, dry_run: bool):
    by_file = {}
    for e in EDITS:
        by_file.setdefault(e["file"], []).append(e)

    total_applied = 0
    total_skipped = 0
    errors = []

    for rel, edits in by_file.items():
        path = root / rel
        print(f"\n=== {rel} ===")

        if not path.is_file():
            errors.append(f"{rel}: файл не найден")
            print("   !!! файл не найден, пропускаю")
            continue

        text = path.read_text(encoding="utf-8")
        original = text

        for e in edits:
            name = e["name"]
            snippet = e["insert"]

            # Уже вставлено?
            probe = _probe(snippet)
            if probe and probe in text:
                print(f"   – уже есть: {name}")
                total_skipped += 1
                continue

            n = text.count(e["anchor"])
            if n != 1:
                msg = f"{rel}: якорь для '{name}' найден {n} раз (нужно ровно 1)"
                errors.append(msg)
                print(f"   !!! {msg}")
                continue

            if e["where"] == "before":
                text = text.replace(e["anchor"], snippet + e["anchor"], 1)
            else:
                text = text.replace(e["anchor"], e["anchor"] + snippet, 1)

            print(f"   + вставлено: {name}")
            total_applied += 1

        if text != original and not dry_run:
            path.write_text(text, encoding="utf-8")

    return total_applied, total_skipped, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".", help="корень сайта")
    ap.add_argument("--dry-run", action="store_true", help="только показать, не менять файлы")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"Нет такой папки: {root}")

    mode = "ПРЕДПРОСМОТР (файлы не изменены)" if args.dry_run else "ПРИМЕНЕНО"
    print(f"=== {mode} ===")
    print(f"Корень: {root}")

    applied, skipped, errors = apply_edits(root, args.dry_run)

    print("\n---------------- итого")
    print(f"Вставлено:      {applied}")
    print(f"Уже было:       {skipped}")
    print(f"Ошибок:         {len(errors)}")

    if errors:
        print("\n!!! НЕ ВСЕ ВСТАВКИ ПРИМЕНЕНЫ:")
        for m in errors:
            print("   ", m)
        print("\nПричина обычно одна: фаил правили вручную и строка-якорь изменилась.")
        sys.exit(1)

    if applied == 0 and skipped:
        print("\nВсё уже на месте — менять нечего.")


if __name__ == "__main__":
    main()
