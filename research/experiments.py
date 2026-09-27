#!/usr/bin/env python3
"""Сравнение конфигураций AFP на обучающей и проверочной части истории."""
import sys
from collections import defaultdict
from dataclasses import replace
from afp_model import Params, summarize
from validate import run_all, fmt, DATASETS_15M, DATASETS_5M


def total(res):
    trades = [t for r in res.values() for t in r.trades]
    ses = sum(r.diag["sessions"] for r in res.values())
    return trades, ses


def line(label, res):
    trades, ses = total(res)
    s = summarize(trades)
    print(f"{label:44s} {fmt(s)}  {len(trades)/max(ses,1):.2f}/сес.")
    return trades


def by_pts(trades):
    g = defaultdict(list)
    for t in trades:
        g[t["pts"]].append(t)
    for k in sorted(g):
        print(f"      баллы {k}: {fmt(summarize(g[k]))}")


if __name__ == "__main__":
    part = sys.argv[1] if len(sys.argv) > 1 else "train"
    sets = DATASETS_15M if (len(sys.argv) < 3 or sys.argv[2] == "15m") else DATASETS_5M
    v1 = replace(Params(), score_v2=False, use_fail_hl=True)
    v2 = replace(Params(), score_v2=True, use_fail_hl=False)
    configs = [
        ("v1 все кандидаты", replace(v1, min_grade=0)),
        ("v1 грейд A", replace(v1, min_grade=4)),
        ("v2 все кандидаты", replace(v2, min_grade=0)),
        ("v2 грейд B (≥3)", replace(v2, min_grade=3)),
        ("v2 грейд A (≥4)", replace(v2, min_grade=4)),
        ("v2 грейд A+ (5)", replace(v2, min_grade=5)),
        ("v2 A, мин. риск 0.5 ATR", replace(v2, min_grade=4, min_risk=0.5)),
        ("v2 A, буфер стопа 0.2 ATR", replace(v2, min_grade=4, stop_buf=0.2)),
        ("v2 A, без ретеста", replace(v2, min_grade=4, use_accept=False)),
        ("v2 A, без отбоя ±2σ", replace(v2, min_grade=4, use_band=False)),
        ("v2 A, допуск уровня 0.15 ATR", replace(v2, min_grade=4, level_tol=0.15)),
        ("v2 A, допуск уровня 0.35 ATR", replace(v2, min_grade=4, level_tol=0.35)),
    ]
    print(f"Часть истории: {part}; наборы: {[d[0] for d in sets]}")
    for label, prm in configs:
        trades = line(label, run_all(prm, sets=sets, part=part))
        if label in ("v1 все кандидаты", "v2 все кандидаты"):
            by_pts(trades)
