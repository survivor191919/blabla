#!/usr/bin/env python3
"""Прогон модели AFP на реальных данных TradingView и сводная статистика.

Данные лежат в research/data/*.csv (в git не коммитятся, выгружены через
TradingView MCP: t, o, h, l, c, v). Запуск: python3 validate.py [режим]
"""
import sys
from collections import defaultdict
from dataclasses import replace

from afp_model import Params, load_csv, resample, run, session_keys, summarize

# (файл, секунд в баре, шаг цены, сдвиг торгового дня в часах)
DATASETS_15M = [
    ("BINANCE_BTCUSDT_15m", 900, 0.01, 0),
    ("BINANCE_ETHUSDT_15m", 900, 0.01, 0),
    ("BINANCE_SOLUSDT_15m", 900, 0.01, 0),
    ("NASDAQ_NVDA_15m", 900, 0.01, 0),
    ("NASDAQ_TSLA_15m", 900, 0.01, 0),
    ("AMEX_SPY_15m", 900, 0.01, 0),
    ("CME_MINI_ES1_15m", 900, 0.25, 2),
]
DATASETS_5M = [
    ("BINANCE_BTCUSDT_5m", 300, 0.01, 0),
    ("BINANCE_ETHUSDT_5m", 300, 0.01, 0),
]
DATASETS_INTRA = [  # график строится из минуток, дельта считается по интрабарам
    ("BINANCE_BTCUSDT_1m", 0.01),
    ("BINANCE_ETHUSDT_1m", 0.01),
]


def load(name, offset):
    bars = load_csv(f"data/{name}.csv")
    return bars, session_keys(bars, offset)


def split(bars, sess, part, frac=0.6):
    """Делит данные по границе сессии: part='train' — первые frac, 'test' — остальное."""
    cut = int(len(bars) * frac)
    while 0 < cut < len(bars) and sess[cut] == sess[cut - 1]:
        cut += 1
    return (bars[:cut], sess[:cut]) if part == "train" else (bars[cut:], sess[cut:])


def run_all(params, sets=DATASETS_15M, part=None):
    out = {}
    for name, sec, tick, off in sets:
        bars, sess = load(name, off)
        if part:
            bars, sess = split(bars, sess, part)
        out[name] = run(bars, sess, sec, tick, params)
    return out


def fmt(s):
    if not s or s.get("n", 0) == 0:
        return "   0 сделок"
    return f"{s['n']:4d} сд.  T1 {s['t1']*100:4.0f}%  T2 {s['t2']*100:4.0f}%  стоп {s['stop']*100:4.0f}%  ср. {s['avg_r']:+.3f}R  сумма {s['sum_r']:+7.1f}R"


def table(results, title):
    print(f"\n=== {title}")
    allt = []
    for name, r in results.items():
        per_day = len(r.trades) / max(r.diag["sessions"], 1)
        print(f"{name:22s} {fmt(summarize(r.trades))}  ({per_day:.1f}/сессию)")
        allt += r.trades
    print(f"{'ВСЕГО':22s} {fmt(summarize(allt))}")
    return allt


def by(trades, key, title):
    g = defaultdict(list)
    for t in trades:
        g[key(t)].append(t)
    print(f"\n--- {title}")
    for k in sorted(g, key=lambda x: str(x)):
        print(f"  {str(k):28s} {fmt(summarize(g[k]))}")


def factors(trades):
    for f in ("delta", "absorb", "div", "rvol", "ctx"):
        by(trades, lambda t, f=f: f"{f}={'да' if t[f] else 'нет'}", f"фактор {f}")
    by(trades, lambda t: f"уровни={t['lv']}", "фактор уровней")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "grades"
    base = Params()
    if mode == "grades":
        for g in (3, 4, 5):
            table(run_all(replace(base, min_grade=g)), f"15m, грейд ≥ {g}")
    elif mode == "factors":
        part = sys.argv[2] if len(sys.argv) > 2 else None
        allt = table(run_all(replace(base, min_grade=0), part=part), f"15m, все кандидаты ({part or 'вся история'})")
        by(allt, lambda t: t["name"], "по сетапам")
        by(allt, lambda t: t["pts"], "по баллам")
        factors(allt)
        by(allt, lambda t: t["state"], "по состоянию аукциона")
        by(allt, lambda t: f"{t['name']} / {'лонг' if t['dir'] > 0 else 'шорт'}", "сетап и направление")
        by(allt, lambda t: "R1<1.5" if t["r1"] < 1.5 else "R1<2.5" if t["r1"] < 2.5 else "R1>=2.5", "по расстоянию до T1")
    elif mode == "intra":
        for name, tick in DATASETS_INTRA:
            m1 = load_csv(f"data/{name}.csv")
            for sec in (300, 900):
                bars, intra = resample(m1, sec)
                sess = session_keys(bars, 0)
                r_i = run(bars, sess, sec, tick, replace(base, min_grade=0), intrabars=intra)
                r_c = run(bars, sess, sec, tick, replace(base, min_grade=0))
                pairs = r_i.diag["delta_pairs"]
                import statistics
                xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
                corr = statistics.correlation(xs, ys) if len(xs) > 2 else float("nan")
                sign = sum((a > 0) == (b > 0) for a, b in pairs) / len(pairs)
                print(f"{name} → {sec//60}m: баров {len(bars)}, корреляция дельты интрабары/оценка {corr:.2f}, совпадение знака {sign*100:.0f}%")
                print(f"   интрабары: {fmt(summarize(r_i.trades))}")
                print(f"   оценка:    {fmt(summarize(r_c.trades))}")
                print(f"   поглощений-сетапов: интрабары {sum(t['name']=='Поглощение' for t in r_i.trades)}, оценка {sum(t['name']=='Поглощение' for t in r_c.trades)}")
