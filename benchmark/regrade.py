# -*- coding: utf-8 -*-
"""保存済みの結果を、現在の採点規則で採点し直して差分を出す。

    python regrade.py                       # results/ の最新
    python regrade.py results/run_....json
    python regrade.py --all

採点規則は結果に効くので、変えたときに過去の結果がどれだけ動くかを見られる
ようにしておく。attempt_log に応答本文と抽出値が残っているので、採点だけは
API を叩かずにやり直せる。

**消費量は直せない。** 誤答と判定された試行はリトライを誘発しており、そこで
使ったトークンは実際に使われている。採点をやり直しても、その分は戻らない。
消費まで直すには測り直すしかない。
"""

import argparse
import json
import sys
from pathlib import Path

import run_benchmark as rb

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"


def truths(run):
    """task_id -> 正答。入力を保存していない世代の結果では引けない。"""
    tasks = (run.get("inputs") or {}).get("tasks")
    if not tasks:
        return None
    return {t["task_id"]: rb.normalize_truth(t["ground_truth"]) for t in tasks}


def regrade(run):
    """試行ごとに採点し直し、判定が変わったものを返す。"""
    table = truths(run)
    if table is None:
        return None
    changed = []
    for row in run["results"]:
        truth = table.get(row["task_id"])
        for attempt in row["attempt_log"]:
            if "answer" not in attempt:
                continue
            now = rb.extract_number(attempt["answer"])
            was = attempt.get("extracted")
            if now == was:
                continue
            changed.append({
                "model": row["model"],
                "condition": row["condition"],
                "task_id": row["task_id"],
                "repeat": row["repeat"],
                "attempt": attempt["attempt"],
                "was_extracted": was,
                "now_extracted": now,
                "was_success": attempt.get("success"),
                "now_success": now is not None and now == truth,
            })
    return changed


def report(path):
    with open(path, encoding="utf-8") as f:
        run = json.load(f)
    changed = regrade(run)
    print(f"\n=== {path.name} ===")
    if changed is None:
        print("  入力を保存していない世代の結果。正答が引けないので採点し直せない。")
        return
    flipped = [c for c in changed if c["was_success"] != c["now_success"]]
    print(f"  試行数 {sum(len(r['attempt_log']) for r in run['results'])}"
          f" / 抽出値が変わった {len(changed)}"
          f" / 正誤が変わった {len(flipped)}")
    if not flipped:
        return
    by = {}
    for c in flipped:
        key = (c["model"], c["task_id"], c["was_success"], c["now_success"])
        by[key] = by.get(key, 0) + 1
    print(f"  {'model':<14}{'task':<10}{'旧':<7}{'新':<7}{'件数'}")
    for (model, task, was, now), n in sorted(by.items()):
        print(f"  {model:<14}{task:<10}{str(was):<7}{str(now):<7}{n}")
    example = flipped[0]
    print(f"  例: {example['condition']} {example['task_id']} rep{example['repeat']}"
          f" attempt{example['attempt']}: {example['was_extracted']} -> {example['now_extracted']}")


def main():
    parser = argparse.ArgumentParser(description="保存済みの結果を採点し直す")
    parser.add_argument("path", nargs="?", help="結果JSON（省略時は最新）")
    parser.add_argument("--all", action="store_true", help="results/ の全ファイル")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if args.all:
        paths = sorted(RESULTS_DIR.glob("run_*.json"))
    elif args.path:
        paths = [Path(args.path)]
    else:
        paths = [sorted(RESULTS_DIR.glob("run_*.json"))[-1]]
    for path in paths:
        report(path)


if __name__ == "__main__":
    main()
