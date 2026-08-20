"""results/ の実行結果JSONを、1試行1行のフラットな表に読み直すだけのモジュール。

測定側（run_benchmark.py / summarize.py）には一切触れない。ここは読むだけ。
要約統計量を先に作らないのが目的なので、集約関数はここには置かない。
"""

import json
import os
import re
import glob

BENCH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(BENCH_DIR, "results")
OUT_DIR = os.path.join(BENCH_DIR, "analysis")

# 見たいのは v3_levels（10水準）の実測run。mock は除く。
SUITE = "v3_levels"


def _short(run_at):
    """run_20260819T222907Z -> 222907Z （表と凡例で使う短い識別子）"""
    m = re.search(r"T(\d{6}Z)$", run_at)
    return m.group(1) if m else run_at


def load_runs(suite=SUITE, include_mock=False):
    """(runs, rows) を返す。suite=None ですべての組を読む。

    runs: run単位のメタ情報のリスト
    rows: 1試行1行のdictのリスト（run間の識別子 run_id 付き）
    """
    runs, rows = [], []
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            try:
                doc = json.load(fh)
            except json.JSONDecodeError:
                continue
        if not isinstance(doc, dict):
            continue
        if suite is not None and doc.get("suite") != suite:
            continue
        if doc.get("mock") and not include_mock:
            continue

        run_id = _short(doc.get("run_at", os.path.basename(path)))
        levels = {c["name"]: c["level"] for c in doc.get("condition_spec", [])}
        meta = {
            "run_id": run_id,
            "path": path,
            "run_at": doc.get("run_at"),
            "suite": doc.get("suite"),
            "prompt_set": doc.get("prompt_set"),
            "models": doc.get("models"),
            "max_attempts": doc.get("max_attempts"),
            "repeats": doc.get("repeats"),
            "conditions": doc.get("conditions"),
            "n_trials": len(doc.get("results", [])),
        }
        runs.append(meta)

        for r in doc.get("results", []):
            log = r.get("attempt_log") or []
            per_attempt_completion = [a.get("completion_tokens") for a in log if a.get("completion_tokens") is not None]
            rows.append(
                {
                    "run_id": run_id,
                    "max_attempts": doc.get("max_attempts"),
                    "repeats_cfg": doc.get("repeats"),
                    "model": r.get("model"),
                    "condition": r.get("condition"),
                    "level": levels.get(r.get("condition")),
                    "task_id": r.get("task_id"),
                    "repeat": r.get("repeat"),
                    "status": r.get("status"),
                    "success": bool(r.get("success")),
                    "tokens_measured": r.get("tokens_measured"),
                    "attempts": r.get("attempts"),
                    "hit_cap": r.get("attempts") == doc.get("max_attempts"),
                    "prompt_tokens": r.get("prompt_tokens"),
                    "completion_tokens": r.get("completion_tokens"),
                    "reasoning_tokens": r.get("reasoning_tokens"),
                    "output_tokens": r.get("output_tokens"),
                    "total_tokens": r.get("total_tokens"),
                    "rot_per_1k": r.get("rot_per_1k"),
                    "latency_sec": r.get("latency_sec"),
                    "final_answer": r.get("final_answer") or "",
                    "first_completion": per_attempt_completion[0] if per_attempt_completion else None,
                    "mean_completion_per_attempt": (
                        sum(per_attempt_completion) / len(per_attempt_completion)
                        if per_attempt_completion else None
                    ),
                    "attempt_completions": per_attempt_completion,
                    "attempt_totals": [a.get("total_tokens") for a in log if a.get("total_tokens") is not None],
                    "attempt_prompts": [a.get("prompt_tokens") for a in log if a.get("prompt_tokens") is not None],
                    "attempt_extracted": [a.get("extracted") for a in log],
                }
            )
    return runs, rows


def levels_in(rows, run_id=None):
    seen = {}
    for r in rows:
        if run_id and r["run_id"] != run_id:
            continue
        seen[r["condition"]] = r["level"]
    return [c for c, _ in sorted(seen.items(), key=lambda kv: (kv[1] is None, kv[1], kv[0]))]


if __name__ == "__main__":
    runs, rows = load_runs()
    for m in runs:
        print(m["run_id"], m["repeats"], "repeats,", len(m["conditions"]), "conds,", m["n_trials"], "trials")
    print("total rows:", len(rows))
