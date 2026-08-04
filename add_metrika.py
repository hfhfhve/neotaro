з#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_metrika.py (v2) — ставит счётчик Яндекс.Метрики во ВСЕ .html файлы neotaro.ru.

Что нового по сравнению с первой версией:
  1. В блок добавлен приём UTM-меток (neoUtm) — метка первого визита запоминается
     навсегда, иначе она теряется при возврате с оплаты и реклама выглядит нулевой.
  2. Метки автоматически дописываются во все внутренние ссылки, чтобы переход
     "лендинг -> /app/" не обнулял источник.
  3. Кабинет (/app/index.html) теперь НЕ трогается. В нём свой расширенный блок
     с neoPurchase/neoUser/neoClientId, и --force затирал бы его, ломая цели оплат.
     Файл узнаётся по строке window.neoPurchase и пропускается со статусом skip_cabinet.

Запуск из корня репозитория:
  python3 add_metrika.py --id 111297297 --dry-run          # показать, ничего не менять
  python3 add_metrika.py --id 111297297 --force            # применить (нужен force, см. ниже)

Про --force: если блок на странице уже есть, скрипт её пропускает. Чтобы заменить
старую версию блока на новую, запуск ОБЯЗАТЕЛЬНО с --force.

Номер счётчика можно задать переменной окружения METRIKA_ID.
Скрипт идемпотентный: повторный запуск не плодит второй счётчик.
"""

import argparse
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- настройки

MARKER = "<!-- neotaro-metrika -->"
MARKER_END = "<!-- /neotaro-metrika -->"

# Версия блока. Меняй при правках BLOCK_TEMPLATE — видно, где какая версия стоит.
BLOCK_VERSION = "2"

# Папки, которые не трогаем
SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "assets"}

# Служебные страницы: считать их визиты смысла нет, только шум в отчётах
SKIP_FILES = {"diag.html"}

# Признак кабинета: там свой расширенный блок, его нельзя перезаписывать
CABINET_SIGNATURE = "window.neoPurchase"


BLOCK_TEMPLATE = """<!-- neotaro-metrika v__VER__ -->
<script type="text/javascript">
   (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
   m[i].l=1*new Date();
   for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
   k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
   (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

   ym(__CID__, "init", {
        clickmap: true,
        trackLinks: true,
        accurateTrackBounce: true,
        webvisor: true
   });

   /* Единая точка для целей. Везде в коде зовём neoGoal('register'),
      а не ym(...) напрямую: номер счётчика остаётся в одном месте,
      и при блокировщике рекламы страница не падает с ошибкой. */
   window.NEO_METRIKA_ID = __CID__;
   window.neoGoal = function(name, params){
     try { if (typeof ym === 'function') ym(__CID__, 'reachGoal', name, params || {}); } catch(e){}
   };
   window.neoHit = function(url, options){
     try { if (typeof ym === 'function') ym(__CID__, 'hit', url, options || {}); } catch(e){}
   };

   /* UTM-метки. Зачем запоминать: при оплате человек уходит на ЮKassa и
      возвращается на neotaro.ru/?paid=1 уже без меток. Если не сохранить метку
      первого визита, оплата запишется на источник "yookassa.ru", а реклама
      будет выглядеть так, будто не принесла ничего. */
   window.neoUtm = (function(){
     var K_FIRST = 'neo_utm_first', K_LAST = 'neo_utm_last';
     var KEYS  = ['utm_source','utm_medium','utm_campaign','utm_content','utm_term'];
     var CLICK = ['yclid','ysclid','gclid','fbclid'];
     function fromUrl(){
       var out = {}, has = false;
       try {
         var q = new URLSearchParams(location.search);
         KEYS.concat(CLICK).forEach(function(k){
           var v = q.get(k);
           if (v) { out[k] = String(v).slice(0,150); has = true; }
         });
       } catch(e){}
       if (!has) {
         try {
           if (document.referrer && document.referrer.indexOf(location.host) === -1) {
             var h = document.referrer.split('/')[2];
             if (h) { out.utm_source = h; out.utm_medium = 'referral'; has = true; }
           }
         } catch(e){}
       }
       return has ? out : null;
     }
     function get(k){ try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch(e){ return null; } }
     function set(k,v){ try { localStorage.setItem(k, JSON.stringify(v)); } catch(e){} }
     var now = fromUrl();
     if (now) {
       now.ts = new Date().toISOString();
       if (!get(K_FIRST)) set(K_FIRST, now);
       set(K_LAST, now);
     }
     var f = get(K_FIRST) || {};
     try {
       if (typeof ym === 'function') ym(__CID__, 'userParams', {
         first_source:   f.utm_source   || '',
         first_medium:   f.utm_medium   || '',
         first_campaign: f.utm_campaign || '',
         first_content:  f.utm_content  || ''
       });
     } catch(e){}
     return function(which){ return get(which === 'last' ? K_LAST : K_FIRST) || {}; };
   })();

   /* Переносим метки в ссылки на кабинет и другие страницы сайта.
      Без этого переход "лендинг -> /app/" Метрика считает новым визитом
      без источника, и вся реклама теряется на первом же клике. */
   document.addEventListener('DOMContentLoaded', function(){
     try {
       var q = location.search;
       if (!q || q.indexOf('utm_') === -1) return;
       var add = q.replace(/^\\?/, '');
       var links = document.querySelectorAll('a[href]');
       for (var i = 0; i < links.length; i++) {
         var a = links[i], h = a.getAttribute('href');
         if (!h) continue;
         if (h.charAt(0) === '#') continue;
         if (/^(mailto:|tel:|javascript:)/i.test(h)) continue;
         if (h.indexOf('utm_') !== -1) continue;
         if (/^https?:\\/\\//i.test(h) && h.indexOf(location.host) === -1) continue;
         a.setAttribute('href', h + (h.indexOf('?') === -1 ? '?' : '&') + add);
       }
     } catch(e){}
   });
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/__CID__" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /neotaro-metrika -->"""


def build_block(counter_id: str) -> str:
    """Собирает блок счётчика. Правь только BLOCK_TEMPLATE — применится ко всем страницам."""
    return BLOCK_TEMPLATE.replace("__CID__", str(counter_id)).replace("__VER__", BLOCK_VERSION)


# ---------------------------------------------------------------- регулярки

# Наш блок любой версии: <!-- neotaro-metrika --> или <!-- neotaro-metrika v2 -->
RE_OUR_BLOCK = re.compile(
    r"[ \t]*<!--\s*neotaro-metrika[^>]*-->.*?<!--\s*/neotaro-metrika\s*-->\s*\n?",
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

RE_MARKER_ANY = re.compile(r"<!--\s*neotaro-metrika[^>]*-->", re.IGNORECASE)
RE_MARKER_CURRENT = re.compile(
    r"<!--\s*neotaro-metrika v" + re.escape(BLOCK_VERSION) + r"\s*-->", re.IGNORECASE
)

# ---------------------------------------------------------------- обработка


def process(html: str, block: str, force: bool):
    """Возвращает (новый_html, статус)."""

    # Кабинет никогда не перезаписываем: там свой расширенный блок
    if CABINET_SIGNATURE in html:
        return html, "skip_cabinet"

    has_any = bool(RE_MARKER_ANY.search(html))
    has_current = bool(RE_MARKER_CURRENT.search(html))

    if has_current and not force:
        return html, "skip_up_to_date"
    if has_any and not force:
        return html, "skip_old_version"

    if not RE_HEAD_OPEN.search(html):
        return html, "error_no_head"

    # 1. Убираем наш блок любой версии
    html, n0 = RE_OUR_BLOCK.subn("", html)

    # 2. Убираем любые прежние счётчики, чтобы не считать визиты дважды
    html, n1 = RE_OLD_METRIKA_SCRIPT.subn("", html)
    html, n2 = RE_OLD_METRIKA_NOSCRIPT.subn("", html)
    removed = n0 + n1 + n2

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
            "  Где взять: metrika.yandex.ru -> счётчик -> номер вверху, вида 111297297\n"
            "  Как передать: python3 add_metrika.py --id 111297297\n"
            "            или METRIKA_ID=111297297 python3 add_metrika.py"
        )

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit("Нет такой папки: %s" % root)

    block = build_block(counter_id)

    files = [
        p
        for p in root.rglob("*.html")
        if not SKIP_DIRS & set(p.relative_to(root).parts)
        and p.name not in SKIP_FILES
    ]

    stats = {
        "added": 0,
        "rewritten": 0,
        "skip_up_to_date": 0,
        "skip_old_version": 0,
        "skip_cabinet": 0,
        "error_no_head": 0,
    }
    changed, problems, cabinets = [], [], []

    for path in sorted(files):
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append((path, "не UTF-8"))
            continue

        new, status = process(original, block, args.force)
        stats[status] = stats.get(status, 0) + 1

        if status == "skip_cabinet":
            cabinets.append(path)
            continue

        if status == "error_no_head":
            problems.append((path, "нет тега <head>"))
            continue

        if new != original:
            changed.append(path)
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")

    # ------------------------------------------------------------ отчёт
    mode = "ПРЕДПРОСМОТР (файлы не изменены)" if args.dry_run else "ПРИМЕНЕНО"
    print("=== %s ===" % mode)
    print("Корень:              %s" % root)
    print("Счётчик:             %s" % counter_id)
    print("Версия блока:        v%s" % BLOCK_VERSION)
    print("Всего .html:         %s" % len(files))
    print("Добавлен блок:       %s" % stats["added"])
    print("Переписан блок:      %s" % stats["rewritten"])
    print("Уже новая версия:    %s" % stats["skip_up_to_date"])
    print("Старая версия, но без --force: %s" % stats["skip_old_version"])
    print("Кабинет, не тронут:  %s" % stats["skip_cabinet"])
    print("Изменено файлов:     %s" % len(changed))

    if stats["skip_old_version"]:
        print("\n!!! На %s страницах стоит СТАРАЯ версия блока."
              " Перезапусти с --force, иначе они останутся без UTM." % stats["skip_old_version"])

    if changed:
        print("\nПервые 15 изменённых:")
        for p in changed[:15]:
            print("  ", p.relative_to(root))
        if len(changed) > 15:
            print("   ... и ещё %s" % (len(changed) - 15))

    if cabinets:
        print("\nПропущено как кабинет (свой блок, не перезаписываем):")
        for p in cabinets[:10]:
            print("  ", p.relative_to(root))

    if problems:
        print("\n!!! Проблемные файлы (%s):" % len(problems))
        for p, why in problems[:20]:
            print("   %s — %s" % (p.relative_to(root), why))


if __name__ == "__main__":
    main()
