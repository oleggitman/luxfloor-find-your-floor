#!/usr/bin/env python3
"""Живые UI-тесты виджета Find Your Floor на lux-floor.de (мобильная + десктопная эмуляция).

Родились из жалобы Ильи (август 2026): на телефоне окно не закрыть. Корень: WP Rocket
delay-JS глотает первый настоящий тап и переигрывает события синтетикой; плюс автофокус
вызывал клавиатуру, плюс мёртвая мобильная вёрстка. Эти тесты держат класс дефекта.

Запуск:
  python3 test_widget_mobile.py                 # против прода как есть (после деплоя)
  python3 test_widget_mobile.py --local         # прод-страница, но widget.js подменяется локальным файлом (до деплоя)
  python3 test_widget_mobile.py --engine webkit # webkit = реальные айфоны (нужен playwright install webkit)
/chat всегда мокается: тесты не пишут мусор в логи бота.
"""
import argparse, json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

SITE = 'https://lux-floor.de/'
WIDGET_URL = 'https://luxfloor-find-your-floor.onrender.com/widget.js'
LOCAL_WIDGET = Path(__file__).resolve().parent / 'widget.js'

RESULTS = []

def check(name, ok, detail=''):
    RESULTS.append((name, ok))
    print(('PASS' if ok else 'FAIL'), name, ('' if ok else ': ' + str(detail)[:160]))

def try_act(fn):
    """Тап/клик, который при таймауте даёт False вместо краха всего прогона."""
    try:
        fn()
        return True
    except Exception:
        return False

def raw_tap(page, sel):
    """Тап по центру элемента без actionability-ожиданий Playwright: пульс-анимация
    кнопки делает её вечно "нестабильной" для page.tap, а реальный палец не ждёт."""
    el = page.query_selector(sel)
    if not el:
        return False
    box = el.bounding_box()
    if not box:
        return False
    page.touchscreen.tap(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    return True

def raw_click(page, sel):
    el = page.query_selector(sel)
    if not el:
        return False
    box = el.bounding_box()
    if not box:
        return False
    page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
    return True

def geom(page):
    return page.evaluate("""() => {
      const g = id => { const el = document.getElementById(id); if (!el) return null;
        const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
        return {display: cs.display, top: r.top, bottom: r.bottom, left: r.left,
                right: r.right, width: r.width, height: r.height}; };
      return {vw: window.innerWidth, vh: window.innerHeight,
              cw: window.visualViewport ? window.visualViewport.width : document.documentElement.clientWidth,
              panel: g('fyf-panel'), btn: g('fyf-btn'), close: g('fyf-close'),
              focused: document.activeElement ? document.activeElement.id : null};
    }""")

def new_page(ctx, local):
    page = ctx.new_page()
    if local:
        body = LOCAL_WIDGET.read_text()
        page.route(WIDGET_URL + '*', lambda r: r.fulfill(
            content_type='application/javascript', body=body))
    page.route('**/chat', lambda r: r.fulfill(content_type='application/json', body=json.dumps(
        {'reply': 'Testantwort vom Mock.', 'session_id': 'ui-test', 'options': ['Chip Antwort A']})))
    page.goto(SITE, wait_until='domcontentloaded', timeout=60000)
    page.wait_for_selector('#fyf-btn', timeout=30000)
    page.wait_for_timeout(1500)
    return page

def panel_open(page):
    d = geom(page)
    return d['panel'] and d['panel']['display'] == 'flex', d

def run_mobile(p, browser_type, local, engine):
    tag = f'[{engine} mobile]'
    iphone = p.devices['iPhone 12']
    browser = browser_type.launch()

    # T1 ручное открытие: нижний лист, крестик >= 44, фокус не в поле ввода
    ctx = browser.new_context(**iphone, locale='de-DE')
    page = new_page(ctx, local)
    raw_tap(page, '#fyf-btn')
    page.wait_for_timeout(700)
    is_open, d = panel_open(page)
    check(f'{tag} T1a тап по кнопке открывает панель', is_open, d)
    if is_open:
        pnl = d['panel']
        check(f'{tag} T1b лист во всю ширину у низа экрана',
              pnl['left'] <= 2 and pnl['right'] >= d['cw'] - 2 and abs(pnl['bottom'] - d['vh']) <= 2, pnl)
        check(f'{tag} T1c компактная высота <= 55% экрана', pnl['height'] <= 0.55 * d['vh'], pnl)
        check(f'{tag} T1d зона крестика >= 42px', d['close'] and d['close']['width'] >= 42 and d['close']['height'] >= 42, d['close'])
        check(f'{tag} T1e фокус не украден в поле ввода', d['focused'] != 'fyf-input', d['focused'])
        check(f'{tag} T1f круглая кнопка спрятана, пока лист открыт', d['btn'] and d['btn']['display'] == 'none', d['btn'])

        # T5 чип шлёт сообщение (мок), лист растёт (до T3, чтобы тапы мимо не увели страницу по ссылке)
        h_before = d['panel']['height']
        chip = page.query_selector('.fyf-chip')
        if chip:
            chip_ok = False
            if raw_tap(page, '.fyf-chip'):
                page.wait_for_timeout(1200)
                chip_ok = 'Testantwort vom Mock' in (page.inner_text('#fyf-msgs') or '')
            check(f'{tag} T5a чип отправляет и приходит ответ', chip_ok)
            h_after = geom(page)['panel']['height']
            check(f'{tag} T5b после вовлечения лист расширился', h_after > h_before + 20, f'{h_before} -> {h_after}')
        else:
            check(f'{tag} T5a чип отправляет и приходит ответ', False, 'чипы не найдены')

        # T2 главный тест жалобы: первый же тап по крестику закрывает, и панель не переоткрывается
        raw_tap(page, '#fyf-close')
        page.wait_for_timeout(700)
        is_open2, d2 = panel_open(page)
        check(f'{tag} T2a тап по крестику закрывает', not is_open2, d2['panel'] if d2 else None)
        page.wait_for_timeout(3500)  # окно переигрывания событий WP Rocket
        is_open3, _ = panel_open(page)
        check(f'{tag} T2b панель не переоткрылась через 3.5с', not is_open3)

        # T3 тап мимо листа закрывает (последним: тап по странице может перейти по ссылке)
        raw_tap(page, '#fyf-btn')
        page.wait_for_timeout(500)
        is_open4, _ = panel_open(page)
        if is_open4:
            page.touchscreen.tap(d['vw'] // 2, 120)  # верх страницы, вне виджета
            page.wait_for_timeout(500)
            is_open5, _ = panel_open(page)
            check(f'{tag} T3 тап по странице закрывает лист', not is_open5)
        else:
            check(f'{tag} T3 тап по странице закрывает лист', False, 'панель не открылась повторно')
    ctx.close()

    # T4 автооткрытие: без фокуса, закрывается тапом мимо
    ctx2 = browser.new_context(**iphone, locale='de-DE')
    page2 = new_page(ctx2, local)
    page2.wait_for_timeout(13000)
    is_open6, d6 = panel_open(page2)
    check(f'{tag} T4a автооткрытие через 12с работает', is_open6, d6)
    if is_open6:
        check(f'{tag} T4b автооткрытие не хватает фокус (клавиатуру)', d6['focused'] != 'fyf-input', d6['focused'])
        page2.touchscreen.tap(d6['vw'] // 2, 120)
        page2.wait_for_timeout(500)
        is_open7, _ = panel_open(page2)
        check(f'{tag} T4c после автооткрытия ушёл одним тапом', not is_open7)
    ctx2.close()
    browser.close()

def run_desktop(p, local):
    tag = '[chromium desktop]'
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='de-DE')
    page = new_page(ctx, local)
    raw_click(page, '#fyf-btn')
    page.wait_for_timeout(700)
    is_open, d = panel_open(page)
    check(f'{tag} T6a клик открывает панель', is_open, d)
    if is_open:
        pnl = d['panel']
        check(f'{tag} T6b геометрия как раньше (320px, справа 20, снизу 220)',
              abs(pnl['width'] - 320) <= 2 and abs((d['vw'] - pnl['right']) - 20) <= 2
              and abs((d['vh'] - pnl['bottom']) - 220) <= 2, pnl)
        try_act(lambda: page.fill('#fyf-input', 'Testfrage', timeout=6000))
        try_act(lambda: page.press('#fyf-input', 'Enter', timeout=6000))
        page.wait_for_timeout(1200)
        check(f'{tag} T6c отправка с клавиатуры работает (мок-ответ виден)',
              'Testantwort vom Mock' in (page.inner_text('#fyf-msgs') or ''))
        raw_click(page, '#fyf-close')
        page.wait_for_timeout(500)
        is_open2, _ = panel_open(page)
        check(f'{tag} T6d крестик закрывает', not is_open2)
    ctx.close()
    browser.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--local', action='store_true', help='подменить widget.js локальным файлом (прогон до деплоя)')
    ap.add_argument('--engine', default='chromium', choices=['chromium', 'webkit', 'both'])
    args = ap.parse_args()
    with sync_playwright() as p:
        engines = ['chromium', 'webkit'] if args.engine == 'both' else [args.engine]
        for eng in engines:
            run_mobile(p, getattr(p, eng), args.local, eng)
        run_desktop(p, args.local)
    failed = [n for n, ok in RESULTS if not ok]
    print(f'\nИТОГ: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS' + (f', FAIL: {len(failed)}' if failed else ''))
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
