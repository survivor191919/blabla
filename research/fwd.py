#!/usr/bin/env python3
"""Направленное преимущество сетапов: средний ход цены через N баров в ATR (в сторону сигнала)."""
import sys
from collections import defaultdict
from dataclasses import replace
from statistics import mean, pstdev
from afp_model import Params, load_csv, session_keys, run, rma_atr
from validate import DATASETS_15M, DATASETS_5M, split

HOR = (2, 4, 8, 16)


def fwd_stats(sets, part, prm):
    rows = []
    for name, sec, tick, off in sets:
        bars = load_csv(f"data/{name}.csv")
        sess = session_keys(bars, off)
        if part != "full":
            bars, sess = split(bars, sess, part)
        C = [b[4] for b in bars]
        atr = rma_atr([b[2] for b in bars], [b[3] for b in bars], C)
        r = run(bars, sess, sec, tick, prm)
        for c in r.candidates:
            i, d = c["bar"], c["dir"]
            if atr[i] is None:
                continue
            fr = {h: ((C[i + h] - C[i]) * d / atr[i]) if i + h < len(C) else None for h in HOR}
            rows.append(dict(c, ds=name, **{f"f{h}": fr[h] for h in HOR}))
    return rows


def show(rows, key, title):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    print(f"\n--- {title}  (средний ход в ATR через {HOR} баров; t-стат для {HOR[-1]})")
    for k in sorted(g, key=str):
        xs = {h: [r[f"f{h}"] for r in g[k] if r[f"f{h}"] is not None] for h in HOR}
        last = xs[HOR[-1]]
        t = mean(last) / (pstdev(last) / len(last) ** 0.5) if len(last) > 2 and pstdev(last) > 0 else 0
        cells = "  ".join(f"{mean(xs[h]):+.3f}" if xs[h] else "   —  " for h in HOR)
        print(f"  {str(k):36s} n={len(g[k]):4d}  {cells}   t={t:+.1f}")


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "full"
    sets = DATASETS_5M if (len(sys.argv) > 2 and sys.argv[2] == "5m") else DATASETS_15M
    prm = replace(Params(), score_v2=True, min_grade=99)  # только кандидаты, без сделок и паузы
    rows = fwd_stats(sets, part, prm)
    show(rows, lambda r: "все", "все кандидаты")
    show(rows, lambda r: r["name"], "по сетапам")
    show(rows, lambda r: (r["name"][:16], "лонг" if r["dir"] > 0 else "шорт"), "сетап × направление")
    show(rows, lambda r: r["pts"], "по баллам v2")
    show(rows, lambda r: ("rvol<1.3" if r["rvol_val"] < 1.3 else "rvol≥1.3"), "по RVOL бара сигнала")
    show(rows, lambda r: (r["name"][:16], "rvol<1.3" if r["rvol_val"] < 1.3 else "rvol≥1.3"), "сетап × RVOL")
    show(rows, lambda r: ("ctx" if r["ctx"] else "против"), "контекст")
    show(rows, lambda r: ("delta" if r["delta"] else "-"), "дельта")
    show(rows, lambda r: ("div" if r["div"] else "-"), "дивергенция")
    show(rows, lambda r: r["ds"], "по инструментам")
