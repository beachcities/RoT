"""失敗試行の思考テキストを、分類規則を組む前に素で眺めるための道具。

規則を先に決めて当てはめると、材料に無い語を数えることになる。まず実物を読む。
"""
import json
import sys
import random
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent


def failed_attempts(path):
    d = json.load(open(BASE / path, encoding="utf-8"))
    out = []
    for r in d["results"]:
        for a in (r.get("attempt_log") or []):
            if a.get("success") is False and (a.get("thinking") or "").strip():
                out.append({
                    "cond": r["condition"], "task": r["task_id"],
                    "repeat": r.get("repeat"), "attempt": a["attempt"],
                    "thinking": a["thinking"],
                })
    return d, out


def main():
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    chars = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
    d, fa = failed_attempts(path)
    print("model:", d["models"], " 失敗試行:", len(fa),
          " 思考総量:", sum(len(x["thinking"]) for x in fa), "字")
    rng = random.Random(0)
    for x in rng.sample(fa, min(n, len(fa))):
        print("\n" + "=" * 70)
        print("%s / %s / rep%s / attempt%d  (%d字)"
              % (x["cond"], x["task"], x["repeat"], x["attempt"], len(x["thinking"])))
        print("-" * 70)
        print(x["thinking"][:chars])


if __name__ == "__main__":
    main()
