# -*- coding: utf-8 -*-
"""A の割合が、規則のどの部分で決まっているかを見る。

一つの数字だけ出すと、規則の恣意性がそのまま数字の信用になる。
条件を厳しくした版を並べて、幅として出す。
"""
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

from quantify_section1 import (RUNS, failed_attempts, segments, GAP, GUESS, WAVER,
                               DATA_OBJ, ASK_OBJ)

# 裸のコード番号（101, 404 …）を対象語から外した版。
# 「perhaps 404 is academic」のような文が、記述の欠落の話なのか
# 仮定を置いた計算なのかを分けられないため、外して下限を見る。
DATA_OBJ_STRICT = re.compile(
    r"\bindustry[_ ]?code|\bcode[_ ]?list|code_definition|unit_definition|"
    r"\bschema\b|\bmapping\b|\bJSIC\b|classification|"
    r"industry (?:name|type|names|category|categories|label)|"
    r"\bunit(?:s)?\b|million|\blabel(?:s|ed)?\b|\bdefinition(?:s)?\b|"
    r"\bfield(?:s)?\b|\bcolumn(?:s)?\b|what (?:each|the) (?:code|field|column|value)|"
    r"stands? for|\bmeans?\b|\bmeaning\b|reference (?:url|link|file)|"
    r"external (?:reference|source|data)|\bdocument(?:ation|ed)?\b|"
    r"意味|定義|対応表|単位",
    re.I,
)

VARIANTS = [
    ("本則（引き金=GAP/GUESS/WAVER、対象=データ語＋コード番号）", None, None),
    ("S1 コード番号を対象から外す", DATA_OBJ_STRICT, None),
    ("S2 引き金を GAP だけにする（明示的な欠落の言及のみ）", None, "gap"),
    ("S3 S1 かつ S2（最も厳しい）", DATA_OBJ_STRICT, "gap"),
]


def run(rows, data_obj, trig_mode):
    data_obj = data_obj or DATA_OBJ
    a = b = c = n = 0
    for r in rows:
        for s in segments(r["thinking"]):
            if trig_mode == "gap":
                trig = bool(GAP.search(s))
            else:
                trig = bool(GAP.search(s) or GUESS.search(s) or WAVER.search(s))
            L = len(s)
            n += L
            if not trig:
                c += L
                continue
            d, k = bool(data_obj.search(s)), bool(ASK_OBJ.search(s))
            if d and k:
                b += L
            elif d:
                a += L
            elif k:
                b += L
            else:
                c += L
    return a, b, c, n


def main():
    print("| 版 | Olmo A割合 | Qwen A割合 |")
    print("|---|---|---|")
    cache = {label: failed_attempts(path)[1] for label, path in RUNS}
    for name, obj, trig in VARIANTS:
        cells = []
        for label, _ in RUNS:
            a, b, c, n = run(cache[label], obj, trig)
            cells.append("%.1f%% (%s/%s字)" % (100 * a / n, f"{a:,}", f"{n:,}"))
        print("| %s | %s | %s |" % (name, cells[0], cells[1]))


if __name__ == "__main__":
    main()
