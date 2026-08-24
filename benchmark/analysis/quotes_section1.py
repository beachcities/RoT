# -*- coding: utf-8 -*-
"""代表実例の候補を、明示的な欠落の言及から拾う。

引用は原文のまま。試行特定子（ラン／水準／タスク／反復／試行番号）を必ず付ける。
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from quantify_section1 import RUNS, failed_attempts, segments, GAP, DATA_OBJ, ASK_OBJ


def main():
    for label, path in RUNS:
        d, rows = failed_attempts(path)
        cands = []
        for r in rows:
            for s in segments(r["thinking"]):
                if GAP.search(s) and DATA_OBJ.search(s) and not ASK_OBJ.search(s):
                    if 60 <= len(s) <= 300:
                        cands.append((r, s))
        # 同じ言い回しの重複を避けて、水準ごとに1件ずつ
        seen = set()
        print("\n## %s  (%s)" % (label, Path(path).name))
        for r, s in cands:
            key = r["cond"]
            if key in seen:
                continue
            seen.add(key)
            print("- %s / %s / rep%s / attempt %d\n  「%s」"
                  % (r["cond"], r["task"], r["repeat"], r["attempt"], s))
        print("  候補総数 %d 件" % len(cands))


if __name__ == "__main__":
    main()
