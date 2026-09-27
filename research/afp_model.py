#!/usr/bin/env python3
"""Эталонная модель Auction Flow Pro на Python.

Повторяет логику auction_flow_pro.pine бар за баром (все бары считаются
закрытыми, как на истории в TradingView), чтобы проверить сигналы на реальных
данных и откалибровать пороги. Нумерация разделов совпадает с docs/SPEC.md.
"""
import csv
import math
from dataclasses import dataclass, field, replace


@dataclass
class Params:
    rvol_ses: int = 20
    abs_rvol: float = 1.5
    abs_delta: float = 0.20
    eff_rvol: float = 2.0
    eff_range: float = 0.7
    div_len: int = 20
    rows_per_atr: int = 40
    va_pct: int = 70
    naked_max: int = 5
    accept_min: int = 30
    min_grade: int = 4          # B = 3, A = 4, A+ = 5; 0 = все кандидаты
    use_abs: bool = True
    use_fail: bool = True
    use_80: bool = True
    use_band: bool = True
    use_accept: bool = True
    abs_confirm: bool = True
    confirm_bars: int = 3
    level_tol: float = 0.25
    stop_buf: float = 0.10
    min_risk: float = 0.30
    max_risk: float = 2.5
    cooldown: int = 3
    max_hold: int = 48
    band1: float = 1.0
    band2: float = 2.0
    # Версия системы баллов (шаг 8): v1 — исходная спецификация, v2 — после проверки.
    score_v2: bool = True
    use_fail_hl: bool = False   # ложный пробой максимума/минимума прошлой сессии


NA = None


def isna(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def load_csv(path):
    with open(path) as f:
        r = csv.DictReader(f)
        return [(int(x["t"]), float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(x["v"])) for x in r]


def resample(bars, sec):
    """Склеивает бары в таймфрейм sec и возвращает (бары, интрабары для каждого бара)."""
    out, intra = [], []
    cur_key, grp = None, []
    for b in bars:
        key = b[0] // sec * sec
        if key != cur_key and grp:
            out.append((cur_key, grp[0][1], max(x[2] for x in grp), min(x[3] for x in grp), grp[-1][4], sum(x[5] for x in grp)))
            intra.append(grp)
            grp = []
        cur_key = key
        grp.append(b)
    if grp:
        out.append((cur_key, grp[0][1], max(x[2] for x in grp), min(x[3] for x in grp), grp[-1][4], sum(x[5] for x in grp)))
        intra.append(grp)
    return out, intra


def session_keys(bars, offset_hours=0):
    """Торговый день: дата UTC со сдвигом (для CME Globex день начинается в 17:00 CT)."""
    return [(b[0] + offset_hours * 3600) // 86400 for b in bars]


def rma_atr(highs, lows, closes, length=14):
    out, tr_hist, prev = [], [], None
    for i in range(len(highs)):
        tr = highs[i] - lows[i] if i == 0 else max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_hist.append(tr)
        if prev is None:
            if len(tr_hist) >= length:
                prev = sum(tr_hist[-length:]) / length
                out.append(prev)
            else:
                out.append(NA)
        else:
            prev = (tr + (length - 1) * prev) / length
            out.append(prev)
    return out


def value_area(m, lo, hi, poc, total, pct):
    target = total * pct / 100.0
    acc = m.get(poc, 0.0)
    up = dn = poc
    while acc < target and (up < hi or dn > lo):
        v_up = m.get(up + 1, 0.0) if up < hi else -1.0
        v_dn = m.get(dn - 1, 0.0) if dn > lo else -1.0
        if v_up >= v_dn:
            up += 1
            acc += v_up
        else:
            dn -= 1
            acc += v_dn
    return up, dn


def levels_near(lv, names, direction, ext, cl, t):
    n, txt = 0, []
    for px, nm in zip(lv, names):
        if isna(px):
            continue
        d = px - ext if direction > 0 else ext - px
        reclaimed = cl > px if direction > 0 else cl < px
        if abs(d) <= t or (0 < d <= 2 * t and reclaimed):
            n += 1
            txt.append(nm)
    return n, ", ".join(txt)


def targets(lv, direction, entry, risk):
    t1 = t2 = NA
    for px in lv:
        if isna(px):
            continue
        d = (px - entry) * direction
        if d >= risk and (t1 is NA or d < (t1 - entry) * direction):
            t1 = px
    if t1 is NA:
        t1 = entry + direction * 1.5 * risk
    t1d = (t1 - entry) * direction
    need2 = max(2 * risk, t1d + 0.5 * risk)
    for px in lv:
        if isna(px):
            continue
        d = (px - entry) * direction
        if d >= need2 and (t2 is NA or d < (t2 - entry) * direction):
            t2 = px
    if t2 is NA:
        t2 = entry + direction * max(3 * risk, t1d + risk)
    return t1, t2


@dataclass
class Result:
    trades: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    diag: dict = field(default_factory=dict)


def run(bars, sess, chart_sec, mintick, p: Params, intrabars=None):
    """Прогоняет индикатор по барам. intrabars[i] — список свечей меньшего ТФ или None."""
    n = len(bars)
    T = [b[0] for b in bars]
    O = [b[1] for b in bars]
    H = [b[2] for b in bars]
    L = [b[3] for b in bars]
    C = [b[4] for b in bars]
    V = [b[5] for b in bars]
    atr_s = rma_atr(H, L, C)

    # Дневные (якорные) бары и ATR прошлого периода для размера строки профиля.
    day_ids, dH, dL, dC = [], [], [], []
    for i in range(n):
        if not day_ids or sess[i] != day_ids[-1]:
            day_ids.append(sess[i]); dH.append(H[i]); dL.append(L[i]); dC.append(C[i])
        else:
            dH[-1] = max(dH[-1], H[i]); dL[-1] = min(dL[-1], L[i]); dC[-1] = C[i]
    d_atr = rma_atr(dH, dL, dC)
    prev_day_atr = {day_ids[k]: (d_atr[k - 1] if k > 0 else NA) for k in range(len(day_ids))}

    accept_bars = max(2, round(p.accept_min * 60 / chart_sec))
    grade_min = p.min_grade
    res = Result()

    # Состояние (аналог var-переменных Pine).
    sumPV = sumV = sumP2V = 0.0
    last_intra_c, last_intra_dir = NA, 1
    cvd_ses = cvd_cont = 0.0
    bar_no = 0
    tod_avg, tod_cnt = {}, {}
    vol_hist, cvd_hist = [], []
    dev_poc = dev_vah = dev_val = NA
    p_poc = p_vah = p_val = p_high = p_low = NA
    ses_high = ses_low = NA
    bin_size = NA
    vp_vol, vp_del = {}, {}
    vp_lo = vp_hi = vp_poc = NA
    vp_poc_v = vp_total = 0.0
    naked = []
    open_loc = 0
    above_cnt = below_cnt = inside_cnt = 0
    acc_up = acc_dn = False
    r80_done = False
    abs_pend = dict(dir=0, hi=NA, lo=NA, bar=0, lv=0, txt="", rvol=NA)
    last_sig_bar = -10 ** 9
    bear_div_hist, bull_div_hist, abs_bull_hist, abs_bear_hist = [], [], [], []
    open_trades = []
    delta_pairs = []
    intra_bars_used = 0

    def barssince(hist):
        for k in range(len(hist) - 1, -1, -1):
            if hist[k]:
                return len(hist) - 1 - k
        return NA

    for i in range(n):
        new_ses = i > 0 and sess[i] != sess[i - 1]
        vol = V[i]
        atr = atr_s[i]

        # 2. VWAP
        if new_ses:
            sumPV = sumV = sumP2V = 0.0
        src = (H[i] + L[i] + C[i]) / 3.0
        sumPV += src * vol; sumV += vol; sumP2V += src * src * vol
        vwap = sumPV / sumV if sumV > 0 else src
        sigma = math.sqrt(max(sumP2V / sumV - vwap * vwap, 0.0)) if sumV > 0 else 0.0
        up1, dn1 = vwap + p.band1 * sigma, vwap - p.band1 * sigma
        up2, dn2 = vwap + p.band2 * sigma, vwap - p.band2 * sigma

        # 3.1 Дельта
        ib = intrabars[i] if intrabars is not None else None
        has_intra = bool(ib)
        intra_dir = []
        buy = sell = 0.0
        if has_intra:
            intra_bars_used += 1
            for (_, o, h, l, c, v) in ib:
                if c > o:
                    d = 1
                elif c < o:
                    d = -1
                elif isna(last_intra_c):
                    d = last_intra_dir
                else:
                    d = 1 if c > last_intra_c else -1 if c < last_intra_c else last_intra_dir
                intra_dir.append(d)
                if d > 0:
                    buy += v
                else:
                    sell += v
                last_intra_c, last_intra_dir = c, d
        else:
            rng = H[i] - L[i]
            buy = vol * (C[i] - L[i]) / rng if rng > 0 else vol * 0.5
            sell = vol - buy
        bar_delta = buy - sell
        flow = buy + sell
        delta_pct = bar_delta / flow if flow > 0 else 0.0
        clv = (C[i] - L[i]) / (H[i] - L[i]) if H[i] > L[i] else 0.5
        if has_intra and vol > 0 and H[i] > L[i]:
            delta_pairs.append((delta_pct, 2 * clv - 1))
        if new_ses:
            cvd_ses = 0.0
        cvd_ses += bar_delta
        cvd_cont += bar_delta

        # 3.2 RVOL по времени сессии
        bar_no = 0 if new_ses else bar_no + 1
        vol_hist.append(vol)
        vol_sma = sum(vol_hist[-20:]) / 20 if len(vol_hist) >= 20 else NA
        tod_base = tod_avg.get(bar_no, NA)
        tod_n = tod_cnt.get(bar_no, 0)
        vol_base = tod_base if tod_n >= 3 else vol_sma
        rvol = vol / vol_base if (not isna(vol_base) and vol_base > 0) else 1.0
        alpha = 2.0 / (p.rvol_ses + 1)
        tod_avg[bar_no] = vol if isna(tod_base) else tod_base + alpha * (vol - tod_base)
        tod_cnt[bar_no] = tod_n + 1

        # 3.3–3.4 Поглощение и дивергенции
        abs_delta_bull = has_intra and rvol >= p.abs_rvol and delta_pct <= -p.abs_delta and clv >= 0.5
        abs_delta_bear = has_intra and rvol >= p.abs_rvol and delta_pct >= p.abs_delta and clv <= 0.5
        effort = (not isna(atr)) and rvol >= p.eff_rvol and (H[i] - L[i]) <= p.eff_range * atr
        prior_high = max(H[i - p.div_len:i]) if i >= p.div_len else NA
        prior_low = min(L[i - p.div_len:i]) if i >= p.div_len else NA
        cvd_high = max(cvd_hist[i - p.div_len:i]) if i >= p.div_len else NA
        cvd_low = min(cvd_hist[i - p.div_len:i]) if i >= p.div_len else NA
        cvd_hist.append(cvd_cont)
        bear_div = (not isna(prior_high)) and H[i] > prior_high and cvd_cont < cvd_high
        bull_div = (not isna(prior_low)) and L[i] < prior_low and cvd_cont > cvd_low
        bear_div_hist.append(bear_div); bull_div_hist.append(bull_div)
        sb = barssince(bear_div_hist); sl = barssince(bull_div_hist)
        bear_div_recent = sb is not NA and sb <= 5
        bull_div_recent = sl is not NA and sl <= 5

        # 4. Профиль
        if new_ses:
            p_poc, p_vah, p_val, p_high, p_low = dev_poc, dev_vah, dev_val, ses_high, ses_low
            ses_high, ses_low = H[i], L[i]
        else:
            ses_high = H[i] if isna(ses_high) else max(ses_high, H[i])
            ses_low = L[i] if isna(ses_low) else min(ses_low, L[i])
        anchor_atr = prev_day_atr.get(sess[i], NA)
        if new_ses or isna(bin_size):
            base = anchor_atr if not isna(anchor_atr) else (atr if not isna(atr) else H[i] - L[i]) * 10
            raw_bin = base / p.rows_per_atr
            bin_size = max(mintick, round(raw_bin / mintick) * mintick)
        if not isna(bin_size):
            if new_ses:
                vp_vol, vp_del = {}, {}
                vp_lo = vp_hi = vp_poc = NA
                vp_poc_v = vp_total = 0.0
            if has_intra:
                segs = [(x[3], x[2], x[5], x[5] * d) for x, d in zip(ib, intra_dir)]
            else:
                segs = [(L[i], H[i], vol, bar_delta)]
            for (lo, hi, v, dv) in segs:
                if v > 0:
                    b0 = math.floor(lo / bin_size)
                    b1 = math.floor(hi / bin_size)
                    nb = b1 - b0 + 1
                    step = math.ceil(nb / 400.0) if nb > 400 else 1
                    cnt = math.ceil(nb / step)
                    sv, sd = v / cnt, dv / cnt
                    for k in range(cnt):
                        key = b0 + k * step
                        nv = vp_vol.get(key, 0.0) + sv
                        vp_vol[key] = nv
                        vp_del[key] = vp_del.get(key, 0.0) + sd
                        if nv > vp_poc_v:
                            vp_poc_v, vp_poc = nv, key
                    vp_lo = b0 if isna(vp_lo) else min(vp_lo, b0)
                    vp_hi = b1 if isna(vp_hi) else max(vp_hi, b1)
                    vp_total += v
            if not isna(vp_poc):
                va_up, va_dn = value_area(vp_vol, vp_lo, vp_hi, vp_poc, vp_total, p.va_pct)
                dev_poc = (vp_poc + 0.5) * bin_size
                dev_vah = (va_up + 1) * bin_size
                dev_val = va_dn * bin_size

        # «Голые» POC
        if p.naked_max > 0:
            if new_ses and not isna(p_poc):
                naked.append(p_poc)
                if len(naked) > p.naked_max:
                    naked.pop(0)
            naked = [px for px in naked if not (L[i] <= px <= H[i])]

        # 5. Состояние аукциона
        has_prev_va = not isna(p_vah) and not isna(p_val)
        if new_ses:
            open_loc = 0 if not has_prev_va else 1 if O[i] > p_vah else -1 if O[i] < p_val else 0
            acc_up = acc_dn = False
        above_cnt = ((1 if new_ses else above_cnt + 1) if has_prev_va and C[i] > p_vah else 0)
        below_cnt = ((1 if new_ses else below_cnt + 1) if has_prev_va and C[i] < p_val else 0)
        inside_cnt = ((1 if new_ses else inside_cnt + 1) if has_prev_va and p_val <= C[i] <= p_vah else 0)
        if above_cnt >= accept_bars:
            acc_up, acc_dn = True, False
        if below_cnt >= accept_bars:
            acc_dn, acc_up = True, False
        if inside_cnt >= accept_bars:
            acc_up = acc_dn = False
        state = 2 if acc_up else -2 if acc_dn else 0 if not has_prev_va else 1 if C[i] > p_vah else -1 if C[i] < p_val else 0

        # 6. Сетапы
        if isna(atr):
            abs_bull_hist.append(False); abs_bear_hist.append(False)
            continue
        tol = p.level_tol * atr
        buf = p.stop_buf * atr
        bull_bar = C[i] > O[i] or clv >= 0.6
        bear_bar = C[i] < O[i] or clv <= 0.4
        ses_mature = bar_no >= 2 * accept_bars
        key_lv = [p_vah, p_val, p_poc, p_high, p_low, vwap, up1, dn1, up2, dn2, dev_poc] + naked
        key_nm = ["VAH пр.", "VAL пр.", "POC пр.", "макс. пр.", "мин. пр.", "VWAP", "VWAP +1σ", "VWAP −1σ",
                  "VWAP +2σ", "VWAP −2σ", "dPOC"] + ["голый POC"] * len(naked)
        tgt_lv = key_lv + [dev_vah, dev_val, ses_high, ses_low]
        n_sup, sup_txt = levels_near(key_lv, key_nm, 1, L[i], C[i], tol)
        n_res, res_txt = levels_near(key_lv, key_nm, -1, H[i], C[i], tol)

        abs_bull = (abs_delta_bull or (effort and clv >= 0.5)) and (n_sup > 0 or (not isna(prior_low) and L[i] <= prior_low))
        abs_bear = (abs_delta_bear or (effort and clv <= 0.5)) and (n_res > 0 or (not isna(prior_high) and H[i] >= prior_high))
        abs_bull_hist.append(abs_bull); abs_bear_hist.append(abs_bear)
        sab, sbe = barssince(abs_bull_hist), barssince(abs_bear_hist)
        abs_bull_recent = sab is not NA and sab <= 2
        abs_bear_recent = sbe is not NA and sbe <= 2

        def failed_breakdown(lv):
            if isna(lv) or i < 2:
                return False
            return (L[i] < lv and C[i] > lv and clv >= 0.5) or (C[i - 1] < lv and C[i - 2] >= lv and C[i] > lv and C[i] > O[i])

        def failed_breakout(lv):
            if isna(lv) or i < 2:
                return False
            return (H[i] > lv and C[i] < lv and clv <= 0.5) or (C[i - 1] > lv and C[i - 2] <= lv and C[i] < lv and C[i] < O[i])

        fb_long_val, fb_long_low = failed_breakdown(p_val), failed_breakdown(p_low)
        fb_short_vah, fb_short_high = failed_breakout(p_vah), failed_breakout(p_high)

        if new_ses:
            r80_done = False
        r80_long = (not r80_done) and open_loc < 0 and inside_cnt == accept_bars
        r80_short = (not r80_done) and open_loc > 0 and inside_cnt == accept_bars
        low_n = min(L[max(0, i - accept_bars + 1):i + 1])
        high_n = max(H[max(0, i - accept_bars + 1):i + 1])

        band_long = ses_mature and sigma > 0 and L[i] <= dn2 and C[i] > dn2 and bull_bar
        band_short = ses_mature and sigma > 0 and H[i] >= up2 and C[i] < up2 and bear_bar

        def retest_long(lv):
            return (not isna(lv)) and i >= 1 and L[i] <= lv + tol and L[i - 1] > lv + tol and C[i] > lv and bull_bar

        def retest_short(lv):
            return (not isna(lv)) and i >= 1 and H[i] >= lv - tol and H[i - 1] < lv - tol and C[i] < lv and bear_bar

        rt_long = state == 2 and (retest_long(p_vah) or retest_long(vwap) or retest_long(dev_poc))
        rt_short = state == -2 and (retest_short(p_val) or retest_short(vwap) or retest_short(dev_poc))

        # Поглощение с подтверждением
        abs_long = abs_short = False
        abs_stop_l = abs_stop_s = NA
        abs_lv_l = abs_lv_s = 0
        abs_txt_l = abs_txt_s = ""
        abs_setup_rvol = NA
        if p.use_abs:
            if p.abs_confirm:
                ap = abs_pend
                if ap["dir"] != 0 and i - ap["bar"] > p.confirm_bars:
                    ap["dir"] = 0
                if ap["dir"] > 0:
                    if C[i] < ap["lo"]:
                        ap["dir"] = 0
                    elif C[i] > ap["hi"]:
                        abs_long, abs_stop_l, abs_lv_l, abs_txt_l, abs_setup_rvol = True, ap["lo"] - buf, ap["lv"], ap["txt"], ap["rvol"]
                        ap["dir"] = 0
                elif ap["dir"] < 0:
                    if C[i] > ap["hi"]:
                        ap["dir"] = 0
                    elif C[i] < ap["lo"]:
                        abs_short, abs_stop_s, abs_lv_s, abs_txt_s, abs_setup_rvol = True, ap["hi"] + buf, ap["lv"], ap["txt"], ap["rvol"]
                        ap["dir"] = 0
                if abs_bull != abs_bear:
                    ap.update(dir=1 if abs_bull else -1, hi=H[i], lo=L[i], bar=i,
                              lv=n_sup if abs_bull else n_res, txt=sup_txt if abs_bull else res_txt, rvol=rvol)
            else:
                abs_long, abs_short = abs_bull and not abs_bear, abs_bear and not abs_bull
                abs_stop_l, abs_stop_s = L[i] - buf, H[i] + buf
                abs_lv_l, abs_lv_s, abs_txt_l, abs_txt_s, abs_setup_rvol = n_sup, n_res, sup_txt, res_txt, rvol

        def score(direction, n_lv, reversal, setup_rvol, name=""):
            d_ok = direction * delta_pct >= 0.10
            a_ok = abs_bull_recent if direction > 0 else abs_bear_recent
            v_ok = bull_div_recent if direction > 0 else bear_div_recent
            c_ok = (state * direction > -2) if reversal else (cvd_ses * direction > 0)
            if p.score_v2:
                # v2: уровень максимум 1 балл; дивергенция не голосует; объём — «проба без
                # инициативы» (RVOL < 1.3) для ответных сетапов, для поглощения объём уже в условии.
                lv_pts = 1 if n_lv >= 1 else 0
                r_ok = True if name == "Поглощение" else rvol < 1.3
                pts = lv_pts + d_ok + a_ok + r_ok + c_ok
            else:
                lv_pts = 2 if n_lv >= 2 else 1 if n_lv >= 1 else 0
                rv = max(rvol, 0.0 if isna(setup_rvol) else setup_rvol)
                r_ok = rv >= 1.3
                pts = lv_pts + d_ok + a_ok + v_ok + r_ok + c_ok
            return pts, dict(lv=lv_pts, delta=d_ok, absorb=a_ok, div=v_ok, rvol=r_ok, ctx=c_ok, rvol_val=rvol)

        cand = {}
        # лонг
        if p.use_80 and r80_long:
            cand[1] = ("Правило 80%", min(low_n, p_val) - buf, max(n_sup, 1), True, NA)
        elif p.use_fail and (fb_long_val or (p.use_fail_hl and fb_long_low)):
            cand[1] = ("Ложный пробой VAL" if fb_long_val else "Ложный пробой минимума", min(L[i], L[i - 1]) - buf, max(n_sup, 1), True, NA)
        elif abs_long:
            cand[1] = ("Поглощение", abs_stop_l, abs_lv_l, True, abs_setup_rvol)
        elif p.use_band and band_long:
            cand[1] = ("Отбой от −2σ", L[i] - buf, max(n_sup, 1), True, NA)
        elif p.use_accept and rt_long:
            cand[1] = ("Ретест после принятия", L[i] - buf, max(n_sup, 1), False, NA)
        # шорт
        if p.use_80 and r80_short:
            cand[-1] = ("Правило 80%", max(high_n, p_vah) + buf, max(n_res, 1), True, NA)
        elif p.use_fail and (fb_short_vah or (p.use_fail_hl and fb_short_high)):
            cand[-1] = ("Ложный пробой VAH" if fb_short_vah else "Ложный пробой максимума", max(H[i], H[i - 1]) + buf, max(n_res, 1), True, NA)
        elif abs_short:
            cand[-1] = ("Поглощение", abs_stop_s, abs_lv_s, True, abs_setup_rvol)
        elif p.use_band and band_short:
            cand[-1] = ("Отбой от +2σ", H[i] + buf, max(n_res, 1), True, NA)
        elif p.use_accept and rt_short:
            cand[-1] = ("Ретест после принятия", H[i] + buf, max(n_res, 1), False, NA)

        if r80_long or r80_short:
            r80_done = True

        # Трекер: сначала ведём открытые сделки по текущему бару.
        still = []
        for tr in open_trades:
            d, en, sp, rk, tp1, tp2 = tr["dir"], tr["entry"], tr["stop_now"], tr["risk"], tr["t1"], tr["t2"]
            r1, r2 = abs(tp1 - en) / rk, abs(tp2 - en) / rk
            h_stop = L[i] <= sp if d > 0 else H[i] >= sp
            h_t1 = H[i] >= tp1 if d > 0 else L[i] <= tp1
            h_t2 = H[i] >= tp2 if d > 0 else L[i] <= tp2
            got1, got2, done, res_r, why = tr["hit1"], False, False, 0.0, ""
            if not tr["hit1"]:
                if h_stop:
                    done, res_r, why = True, -1.0, "стоп"
                elif h_t1:
                    got1 = True
                    if h_t2:
                        got2, done, res_r, why = True, True, 0.5 * r1 + 0.5 * r2, "T2"
                    else:
                        tr["hit1"], tr["stop_now"] = True, en
            else:
                if h_stop:
                    done, res_r, why = True, 0.5 * r1, "безубыток"
                elif h_t2:
                    got2, done, res_r, why = True, True, 0.5 * r1 + 0.5 * r2, "T2"
            if not done and i - tr["bar"] >= p.max_hold:
                r_now = (C[i] - en) * d / rk
                done, res_r, why = True, (0.5 * r1 + 0.5 * r_now) if got1 else r_now, "время"
            if done:
                tr.update(got1=got1, got2=got2, r=res_r, exit=why, exit_bar=i)
                res.trades.append(tr)
            else:
                still.append(tr)
        open_trades = still

        # Итоговый сигнал
        if cand and i - last_sig_bar > p.cooldown:
            scored = {}
            for d, (name, stop, n_lv, rev, srv) in cand.items():
                pts, factors = score(d, n_lv, rev, srv, name)
                scored[d] = (pts, factors)
                res.candidates.append(dict(bar=i, t=T[i], dir=d, name=name, pts=pts, **factors))
            s_l = scored[1][0] if 1 in scored else -1
            s_s = scored[-1][0] if -1 in scored else -1
            direction = 1 if (s_l >= grade_min and s_l > s_s) else -1 if (s_s >= grade_min and s_s > s_l) else 0
            if direction != 0:
                name, stop, n_lv, rev, srv = cand[direction]
                entry = C[i]
                stop_px = min(stop, entry - p.min_risk * atr) if direction > 0 else max(stop, entry + p.min_risk * atr)
                risk = abs(entry - stop_px)
                if 0 < risk <= p.max_risk * atr:
                    t1, t2 = targets(tgt_lv, direction, entry, risk)
                    open_trades.append(dict(bar=i, t=T[i], dir=direction, name=name, pts=scored[direction][0],
                                            entry=entry, stop=stop_px, stop_now=stop_px, risk=risk, t1=t1, t2=t2,
                                            r1=abs(t1 - entry) / risk, r2=abs(t2 - entry) / risk, hit1=False,
                                            state=state, **scored[direction][1]))
                    last_sig_bar = i

    res.diag = dict(bars=n, sessions=len(set(sess)), intra_bars=intra_bars_used, delta_pairs=delta_pairs,
                    open_at_end=len(open_trades))
    return res


def summarize(trades):
    if not trades:
        return dict(n=0)
    n = len(trades)
    return dict(n=n,
                t1=sum(t["got1"] for t in trades) / n,
                t2=sum(t["got2"] for t in trades) / n,
                avg_r=sum(t["r"] for t in trades) / n,
                sum_r=sum(t["r"] for t in trades),
                stop=sum(t["exit"] == "стоп" for t in trades) / n)
