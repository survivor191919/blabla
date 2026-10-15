#!/usr/bin/env python3
"""Генератор печатных шаблонов планов дня (A4) -> planner.html. PDF делается через Chromium."""

TYPES = {
    "A": {"name": "Обычная неделя", "accent": "#2f6f8f", "soft": "#e6f1f6"},
    "B": {"name": "Отчётная неделя", "accent": "#b5532a", "soft": "#fbece4"},
}

MORNING = [(h, f"{h:02d}:00") for h in range(6, 12)]
DAY = [(h, f"{h:02d}:00") for h in range(12, 18)]
EVENING = [(h, f"{h:02d}:00") for h in range(18, 24)]


def rows(hours, n=1):
    out = ""
    for _, label in hours:
        out += f'<div class="row"><span class="t">{label}</span><span class="w"></span><span class="ck"></span></div>'
    return out


def block(title, icon, hint, hours):
    return f"""
    <div class="blk">
      <div class="bh"><b>{icon} {title}</b><i>{hint}</i></div>
      {rows(hours)}
    </div>"""


def lines(n, cls="ln"):
    return "".join(f'<div class="{cls}"></div>' for _ in range(n))


def boxes(n):
    return "".join('<span class="bx"></span>' for _ in range(n))


def card(title, body, cls=""):
    return f'<div class="card {cls}"><div class="ct">{title}</div>{body}</div>'


def habit_tracker(items):
    return "".join(f'<div class="hb"><span class="bx"></span>{i}</div>' for i in items)


def page(kind, day_title, subtitle, morning_hint, day_hint, evening_hint, side):
    t = TYPES[kind]
    return f"""
<section class="page" style="--ac:{t['accent']};--soft:{t['soft']}">
  <header>
    <div class="tag">{t['name']}</div>
    <h1>{day_title}</h1>
    <div class="sub">{subtitle}</div>
    <div class="meta">
      <span>Дата: <u>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</u></span>
      <span>Энергия: ☐ низкая ☐ средняя ☐ высокая</span>
      <span>Настроение: ☹ 😐 🙂</span>
    </div>
  </header>
  <div class="grid">
    <main>
      {block("УТРО", "🌅", morning_hint, MORNING)}
      {block("ДЕНЬ", "☀️", day_hint, DAY)}
      {block("ВЕЧЕР", "🌙", evening_hint, EVENING)}
      <div class="legend">Подсказка: пары — обвести рамкой · учёба — заштриховать · отдых — волна ～</div>
    </main>
    <aside>{side}</aside>
  </div>
</section>"""


# ---------- боковые панели ----------
def mit(n=3):
    return card("🎯 ГЛАВНЫЕ ЗАДАЧИ (макс. 3)", "".join(f'<div class="mi"><span class="bx big"></span><span class="ln grow"></span></div>' for _ in range(n)))


def pairs_card():
    return card("🎓 ПАРЫ СЕГОДНЯ", "".join('<div class="pr"><span class="ln s"></span><span class="ln grow"></span></div>' for _ in range(4)) + '<div class="cap">время · предмет / ауд. / что принести</div>')


def todo(n, title="✅ ВТОРОСТЕПЕННОЕ"):
    return card(title, "".join(f'<div class="mi"><span class="bx"></span><span class="ln grow"></span></div>' for _ in range(n)))


def pomodoro():
    return card("🍅 ПОМОДОРО (25/5)", f'<div class="boxes">{boxes(12)}</div>')


def water_sleep():
    return card("💧 ТЕЛО", f"""
      <div class="cap">Вода</div><div class="boxes">{boxes(8)}</div>
      <div class="cap">Сон: лёг ____ · встал ____ · ☐ 7+ ч</div>
      <div class="cap">Движение: ☐ прогулка ☐ зарядка ☐ зал</div>""")


def summary():
    return card("🌗 ИТОГ ДНЯ", f"""
      <div class="cap">Что получилось:</div>{lines(2)}
      <div class="cap">Что перенёс и почему:</div>{lines(2)}
      <div class="cap">Завтра первым делом:</div>{lines(1)}""")


def week_plan():
    return card("🗓 ЦЕЛИ НЕДЕЛИ", "".join(f'<div class="mi"><span class="bx"></span><span class="ln grow"></span></div>' for _ in range(4)) +
                '<div class="cap">Дедлайны недели:</div>' + lines(2))


def friday_review():
    return card("🏁 ИТОГИ НЕДЕЛИ", f"""
      <div class="cap">Закрыто:</div>{lines(2)}
      <div class="cap">«Хвосты» → на выходные / следующую неделю:</div>{lines(3)}
      <div class="cap">Оценка недели: ☐1 ☐2 ☐3 ☐4 ☐5</div>""")


def reporting_table(rows_n=5, title="📑 СДАЧА / ЗАЧЁТЫ / ОТЧЁТНОСТЬ"):
    head = '<div class="tb th"><span>Предмет</span><span>Что сдать</span><span>Срок</span><span>Статус</span></div>'
    body = "".join('<div class="tb"><span class="ln"></span><span class="ln"></span><span class="ln"></span><span class="st">☐ ☐ ☑</span></div>' for _ in range(rows_n))
    return card(title, head + body + '<div class="cap">Статус: ☐ не начат · ☐ в процессе · ☑ сдано</div>')


def exam_prep():
    return card("🧠 ПОДГОТОВКА (по приоритету)", "".join(
        '<div class="mi"><span class="bx"></span><span class="ln grow"></span><span class="ln s"></span></div>' for _ in range(4)
    ) + '<div class="cap">тема / что сделать · сколько часов</div>')


def free_zone():
    return card("🎈 ДЛЯ СЕБЯ", f"""
      <div class="cap">Хочу сегодня (хобби, друзья, спорт, отдых):</div>{lines(3)}""")


def chores():
    return card("🧺 БЫТ / ДЕЛА", "".join(f'<div class="mi"><span class="bx"></span><span class="ln grow"></span></div>' for _ in range(4)) +
                '<div class="cap">☐ уборка ☐ стирка ☐ продукты ☐ звонок родным</div>')


def idea_box():
    return card("💡 ЗАМЕТКИ / ИДЕИ", lines(4))


# ---------- страницы ----------
pages = []

# Обычная неделя
pages.append(page("A", "Понедельник", "Старт недели: настроиться и расставить приоритеты",
    "Подъём · зарядка · завтрак · обзор недели (10 мин)", "Пары / учёба · обед · не забыть перерыв", "Домашка · спорт · отдых · план на завтра",
    week_plan() + pairs_card() + mit() + water_sleep() + summary()))

pages.append(page("A", "Вторник · Среда · Четверг", "Рабочие дни: ритм и фокус",
    "Подъём · завтрак · дорога · повторить лекции", "Пары · обед · самоподготовка", "Дом. задания · личное время · сон до 23:00",
    pairs_card() + mit() + todo(4) + pomodoro() + water_sleep() + summary()))

pages.append(page("A", "Пятница", "Закрыть хвосты и подвести итоги недели",
    "Подъём · завтрак · разобрать «хвосты»", "Пары · обед · сдача мелких работ", "Итоги недели · отдых · планы на выходные",
    pairs_card() + mit() + friday_review() + todo(3, "✅ ДО ВЫХОДНЫХ") + water_sleep()))

# Отчётная неделя
pages.append(page("B", "Понедельник", "Старт отчётной недели: составить карту сдачи",
    "Подъём · завтрак · выписать ВСЕ сдачи и сроки", "Пары · приоритет: ближайший дедлайн", "Подготовка по плану · сон ≥ 7 ч",
    reporting_table(5) + pairs_card() + mit() + pomodoro() + water_sleep() + summary()))

pages.append(page("B", "Вторник · Среда · Четверг", "Режим штурма: сдаём и готовимся",
    "Подъём · завтрак · самое сложное первым делом", "Пары / сдачи · обед · блок подготовки", "Повторение · лёгкая нагрузка · сон",
    reporting_table(4, "📑 ДЕДЛАЙНЫ СЕГОДНЯ / ЗАВТРА") + exam_prep() + mit() + pomodoro() + water_sleep() + summary()))

pages.append(page("B", "Пятница", "Финиш отчётной недели: добить и выдохнуть",
    "Подъём · завтрак · последние сдачи", "Пары / пересдачи · обед · закрыть долги", "Итоги · награда себе · полноценный отдых",
    reporting_table(4, "📑 ЧТО ЕЩЁ НЕ СДАНО") + friday_review() + mit(2) + water_sleep()))

# Выходной (универсальный)
pages.append(page("A", "Суббота · Воскресенье", "Восстановление + немного подготовки к новой неделе",
    "Подъём без будильника · завтрак · зарядка", "Хобби · встречи · прогулка · 1 блок учёбы (по желанию)", "Отдых · подготовка вещей · план на понедельник",
    free_zone() + chores() + mit(2) + card("📚 ХВОСТЫ УЧЁБЫ (максимум 1–2 блока)", "".join('<div class="mi"><span class="bx"></span><span class="ln grow"></span></div>' for _ in range(3))) +
    card("🗓 ПЕРЕД НОВОЙ НЕДЕЛЕЙ", '<div class="cap">Тип недели: ☐ обычная ☐ отчётная</div><div class="cap">☐ расписание проверено ☐ вещи готовы ☐ дедлайны выписаны</div>') + idea_box()))

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin:0; font-family: "DejaVu Sans","Segoe UI",Arial,sans-serif; color:#222; font-size:9pt; }
.page { width:210mm; height:297mm; padding:10mm 10mm 8mm; page-break-after:always; overflow:hidden; border-top:6mm solid var(--ac); }
header { margin-bottom:3mm; }
.tag { display:inline-block; background:var(--ac); color:#fff; padding:1mm 3mm; border-radius:3mm; font-size:8pt; letter-spacing:.5pt; text-transform:uppercase; }
h1 { margin:1.5mm 0 0; font-size:20pt; color:var(--ac); }
.sub { color:#555; font-style:italic; margin-bottom:2mm; }
.meta { display:flex; gap:6mm; font-size:8pt; color:#444; border-bottom:.4mm solid var(--ac); padding-bottom:2mm; }
.grid { display:grid; grid-template-columns: 1.25fr 1fr; gap:5mm; height: calc(297mm - 10mm - 8mm - 6mm - 27mm); }
.blk { margin-bottom:2.5mm; border:.3mm solid var(--ac); border-radius:2mm; overflow:hidden; }
.bh { background:var(--soft); padding:1mm 2mm; display:flex; justify-content:space-between; align-items:baseline; }
.bh b { color:var(--ac); } .bh i { font-size:6.5pt; color:#666; max-width:62%; text-align:right; }
.row { display:grid; grid-template-columns: 11mm 1fr 6mm; height:8.2mm; border-top:.2mm solid #ccc; }
.row .t { font-size:7.5pt; color:var(--ac); padding:1.2mm 0 0 1.5mm; border-right:.2mm solid #ccc; }
.row .ck { border-left:.2mm solid #ccc; position:relative; } .row .ck::after { content:""; position:absolute; left:1.3mm; top:2.2mm; width:3.2mm; height:3.2mm; border:.3mm solid #888; border-radius:.6mm; }
.legend { font-size:6.5pt; color:#777; text-align:center; }
aside { display:flex; flex-direction:column; gap:2.5mm; }
.card { border:.3mm solid var(--ac); border-radius:2mm; padding:1.5mm 2mm 2mm; }
.ct { font-weight:bold; color:var(--ac); font-size:8pt; margin-bottom:1.2mm; }
.cap { font-size:6.8pt; color:#666; margin:1mm 0 0; }
.ln { display:block; height:5.5mm; border-bottom:.2mm solid #999; }
.mi { display:flex; align-items:flex-end; gap:1.5mm; margin-bottom:.4mm; } .mi .ln { height:5.2mm; }
.grow { flex:1; } .s { width:16mm; flex:none; }
.bx { display:inline-block; width:3.2mm; height:3.2mm; border:.3mm solid #888; border-radius:.6mm; margin-right:1mm; vertical-align:middle; flex:none; margin-bottom:1mm; }
.bx.big { width:4mm; height:4mm; }
.boxes { display:flex; flex-wrap:wrap; gap:1.2mm; }
.boxes .bx { width:4.2mm; height:4.2mm; border-radius:1mm; margin:0; }
.pr { display:flex; gap:2mm; margin-bottom:.3mm; }
.tb { display:grid; grid-template-columns:1fr 1.4fr 14mm 13mm; gap:1.5mm; align-items:end; margin-bottom:.3mm; }
.th { font-size:6.5pt; color:#666; border-bottom:.2mm solid var(--ac); }
.st { font-size:7pt; color:#888; }
.hb { display:inline-flex; align-items:center; margin-right:2mm; }
@media screen { body { background:#ddd; } .page { background:#fff; margin:6mm auto; box-shadow:0 0 4mm #0003; } }
"""

html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Планер дня — студенческий</title><style>{CSS}</style></head><body>
{''.join(pages)}
</body></html>"""

open("planner.html", "w", encoding="utf-8").write(html)
print("ok", len(pages), "pages")
