#!/usr/bin/env python3
"""Минимальный статический линтер для Pine Script v6.

Компилятор Pine есть только у TradingView, поэтому здесь ловятся самые частые
ошибки, которые можно найти без него:

* строки-продолжения с отступом, кратным 4 (Pine примет их за новый блок);
* зарезервированные слова в роли имён переменных;
* локальные переменные, затеняющие глобальные (ошибка «Shadowing variable»);
* переприсваивание (:=, +=) необъявленной переменной;
* plot/plotshape/fill/bgcolor/barcolor/alertcondition вне глобальной области;
* вызовы ta.* внутри локальных блоков (нестабильная история серий);
* идентификаторы, которые нигде не объявлены и не являются встроенными (опечатки).

Использование: python3 tools/pine_lint.py auction_flow_pro.pine
"""
import re
import sys

RESERVED = {
    "and", "or", "not", "if", "else", "for", "to", "by", "in", "while", "switch",
    "var", "varip", "import", "export", "method", "type", "enum", "true", "false",
    "na", "series", "simple", "const", "input", "break", "continue",
}
TYPES = {"int", "float", "bool", "string", "color", "line", "label", "box", "table",
         "linefill", "polyline", "chart.point", "array", "map", "matrix"}
GLOBAL_ONLY = ("plot(", "plotshape(", "plotchar(", "plotarrow(", "plotcandle(", "plotbar(",
               "fill(", "bgcolor(", "barcolor(", "alertcondition(", "hline(", "indicator(")
BUILTINS = {
    # пространства имён и переменные
    "ta", "math", "str", "array", "map", "matrix", "request", "input", "syminfo", "timeframe",
    "barstate", "color", "line", "label", "box", "table", "plot", "shape", "location", "size",
    "position", "text", "extend", "xloc", "yloc", "format", "display", "alert", "barmerge",
    "open", "high", "low", "close", "volume", "hlc3", "hl2", "ohlc4", "time", "bar_index",
    "na", "nz", "true", "false", "int", "float", "bool", "string", "indicator", "plotshape",
    "bgcolor", "barcolor", "fill", "alertcondition", "chart", "session", "dayofweek",
    "last_bar_index", "position",
}
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\.]*")


def strip_strings_comments(line):
    out, i, q = [], 0, None
    while i < len(line):
        ch = line[i]
        if q:
            if ch == "\\":
                i += 2
                continue
            if ch == q:
                q = None
        else:
            if ch in "\"'":
                q = ch
                out.append("STR")
            elif line.startswith("//", i):
                break
            else:
                out.append(ch)
        i += 1
    return "".join(out).rstrip()


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def main(path):
    raw = open(path, encoding="utf-8").read().split("\n")
    code = [strip_strings_comments(l) for l in raw]
    problems = []

    # 1. Логические строки: склейка продолжений.
    logical = []  # (номер первой строки, отступ, текст)
    i = 0
    while i < len(code):
        line = code[i]
        if not line.strip():
            i += 1
            continue
        start, ind, text = i, indent_of(line), line.strip()
        depth = text.count("(") + text.count("[") - text.count(")") - text.count("]")
        while depth > 0 or re.search(r"(\+|-|\*|/|,|\(|\band|\bor|\?|:)$", text) and not text.endswith(":="):
            i += 1
            if i >= len(code):
                break
            nxt = code[i]
            if not nxt.strip():
                continue
            if indent_of(nxt) % 4 == 0:
                problems.append(f"{i+1}: продолжение строки {start+1} с отступом, кратным 4")
            text += " " + nxt.strip()
            depth = text.count("(") + text.count("[") - text.count(")") - text.count("]")
        if ind % 4 != 0:
            problems.append(f"{start+1}: отступ {ind} не кратен 4 у начала оператора")
        logical.append((start + 1, ind, text))
        i += 1

    # 2. Объявления.
    globals_, declared = {}, set()
    decl_re = re.compile(r"^(?:var\s+|varip\s+)?(?:(?:[a-z]+(?:<[^>]+>)?|chart\.point)\s+)?([A-Za-z_]\w*)\s*=(?!=)")
    tuple_re = re.compile(r"^\[([^\]]+)\]\s*=(?!=)")
    func_re = re.compile(r"^([A-Za-z_]\w*)\s*\(([^)]*)\)\s*=>")
    for_re = re.compile(r"^for\s+(?:\[([^\]]+)\]|([A-Za-z_]\w*))\s*(?:=|in)\b")
    locals_ = []  # (строка, имя)
    for ln, ind, text in logical:
        names = []
        m = func_re.match(text)
        if m:
            declared.add(m.group(1))
            if ind == 0:
                globals_[m.group(1)] = ln
            for prm in m.group(2).split(","):
                prm = prm.strip()
                if prm:
                    pname = prm.split()[-1].split("=")[0].strip()
                    declared.add(pname)
                    if pname in RESERVED:
                        problems.append(f"{ln}: параметр «{pname}» — зарезервированное слово")
            continue
        m = for_re.match(text)
        if m:
            vars_ = (m.group(1) or m.group(2)).split(",")
            for v in vars_:
                v = v.strip()
                declared.add(v)
                locals_.append((ln, v))
            continue
        m = tuple_re.match(text)
        if m:
            names = [x.strip() for x in m.group(1).split(",")]
        else:
            m = decl_re.match(text)
            if m and not re.match(r"^[A-Za-z_]\w*\s*:=", text):
                names = [m.group(1)]
        for n in names:
            if n in RESERVED or n in TYPES:
                problems.append(f"{ln}: «{n}» — зарезервированное слово, нельзя использовать как имя")
            declared.add(n)
            if ind == 0:
                if n in globals_:
                    problems.append(f"{ln}: глобальная «{n}» объявлена повторно (строка {globals_[n]})")
                globals_[n] = ln
            else:
                locals_.append((ln, n))
    for ln, n in locals_:
        if n in globals_:
            problems.append(f"{ln}: локальная «{n}» затеняет глобальную (строка {globals_[n]})")

    # 3. Переприсваивания и прочие проверки по логическим строкам.
    for ln, ind, text in logical:
        m = re.match(r"^([A-Za-z_]\w*)\s*(:=|\+=|-=|\*=|/=)", text)
        if m and m.group(1) not in declared:
            problems.append(f"{ln}: «{m.group(1)}» переприсваивается, но не объявлена")
        if ind > 0 and text.startswith(GLOBAL_ONLY):
            problems.append(f"{ln}: {text.split('(')[0]} можно вызывать только в глобальной области")
        if ind > 0 and re.search(r"\bta\.\w+\(", text):
            problems.append(f"{ln}: вызов ta.* в локальном блоке (проверьте последовательность вызова)")
        if re.search(r"\bbool\s+\w+\s*=\s*na\b", text):
            problems.append(f"{ln}: в v6 bool не может быть na")
        m = re.match(r"^for\s+\w+\s*=\s*0\s+to\s+(.+?)\s*-\s*1$", text)
        if m:
            problems.append(f"{ln}: цикл «0 to {m.group(1)} - 1» — убедитесь, что {m.group(1)} > 0 (иначе цикл пойдёт вниз)")

    # 4. Необъявленные идентификаторы (опечатки).
    named_args = set()
    for _, _, text in logical:
        for m in re.finditer(r"[(,]\s*([A-Za-z_]\w*)\s*=(?!=)", text):
            named_args.add(m.group(1))
    unknown = {}
    for ln, _, text in logical:
        for tok in TOKEN_RE.findall(text):
            root = tok.split(".")[0]
            if (root in declared or root in BUILTINS or root in RESERVED or root in TYPES
                    or root in named_args or root.isupper() or re.fullmatch(r"[A-Z_0-9]+", root)):
                continue
            unknown.setdefault(root, ln)
    for tok, ln in sorted(unknown.items(), key=lambda x: x[1]):
        problems.append(f"{ln}: «{tok}» не объявлен и не встроенный (опечатка?)")

    for p in problems:
        print(p)
    print(f"-- логических строк: {len(logical)}, глобальных имён: {len(globals_)}, замечаний: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "auction_flow_pro.pine"))
