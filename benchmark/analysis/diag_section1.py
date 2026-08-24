# -*- coding: utf-8 -*-
"""分類規則が一語に依存していないか、誤爆していないかを見る。

規則で数えた以上、その規則がどこで当たっているかを開示できないと数字が読めない。
"""
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

from quantify_section1 import (RUNS, failed_attempts, segments, classify,
                               GAP, GUESS, WAVER, DATA_OBJ, ASK_OBJ)


def main():
    for label, path in RUNS:
        d, rows = failed_attempts(path)
        trig = Counter()
        obj = Counter()
        a_chars = 0
        a_by_trig = Counter()
        samples = {"A": [], "C_with_data": []}
        for r in rows:
            for s in segments(r["thinking"]):
                kind, _ = classify(s)
                if kind == "A":
                    a_chars += len(s)
                    for m in GAP.findall(s):
                        pass
                    g = GAP.search(s)
                    gu = GUESS.search(s)
                    w = WAVER.search(s)
                    which = ("GAP" if g else "") + ("+GUESS" if gu else "") + ("+WAVER" if w else "")
                    a_by_trig[which.strip("+")] += len(s)
                    if g:
                        trig["GAP:" + g.group(0).lower()[:28]] += 1
                    elif gu:
                        trig["GUESS:" + gu.group(0).lower()[:28]] += 1
                    elif w:
                        trig["WAVER:" + w.group(0).lower()[:28]] += 1
                    o = DATA_OBJ.search(s)
                    if o:
                        obj[o.group(0).lower()[:24]] += 1
                    if len(samples["A"]) < 400:
                        samples["A"].append((r, s))
                elif kind == "C" and DATA_OBJ.search(s) and len(s) > 40:
                    if len(samples["C_with_data"]) < 200:
                        samples["C_with_data"].append((r, s))

        print("\n## %s" % label)
        print("A の文字数を引き金の種類で割ると:")
        for k, v in a_by_trig.most_common():
            print("   %-16s %8s 字 (%.1f%%)" % (k, f"{v:,}", 100 * v / a_chars))
        print("A で当たった引き金 上位10:")
        for k, v in trig.most_common(10):
            print("   %-40s %d 件" % (k, v))
        print("A で当たった対象語 上位10:")
        for k, v in obj.most_common(10):
            print("   %-28s %d 件" % (k, v))
        print("\nA と判定された文の例（先頭から間隔をあけて5件）:")
        step = max(1, len(samples["A"]) // 5)
        for r, s in samples["A"][::step][:5]:
            print("   [%s/%s/att%d] %s" % (r["cond"], r["task"], r["attempt"], s[:170]))
        print("\nC だがデータ語を含む文の例（誤って落としていないかの確認）:")
        step = max(1, len(samples["C_with_data"]) // 4)
        for r, s in samples["C_with_data"][::step][:4]:
            print("   [%s/%s/att%d] %s" % (r["cond"], r["task"], r["attempt"], s[:170]))


if __name__ == "__main__":
    main()
