# -*- coding: utf-8 -*-
"""既存の結果ファイルに、後から付けられる範囲の指紋を付ける。

    python backfill_fingerprints.py [--dry-run]

指紋を持たない世代の結果ファイルは、**入力の中身を保存していない**。データと
タスクの本文は結果ファイルから復元できないので、そこは復元不能として明記する。
付けられるのは、結果ファイルに残っていた情報（組の名前、プロンプト全文、
条件の仕様、設定値）から計算できる分だけ。

現在の suites/ の中身をハッシュして当てはめることはしない。組は編集されている
ので、いま同じ名前のファイルにある内容が、そのとき投げた内容だとは言えない。
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import run_benchmark as rb

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

# 結果ファイルに保存されていないため、後から復元できないもの。
UNRECOVERABLE = {
    "conditions_data": "各データ条件の本文。結果ファイルに保存されていない",
    "tasks": "タスクの問い文と正答。task_id しか保存されていない",
}


def backfill(run):
    """付けられる指紋を組み立てて返す。すでに指紋があるものは None。"""
    if "fingerprint" in run:
        return None

    recoverable = {
        "algorithm": f"sha256[:{rb.FINGERPRINT_BITS}] of compact JSON",
        "suite": run.get("suite"),
        "prompt_set": run.get("prompt_set"),
        "conditions": run.get("conditions"),
        "models": run.get("models"),
        "settings": {
            "max_attempts": run.get("max_attempts"),
            "repeats": run.get("repeats"),
        },
        "mock": run.get("mock"),
    }
    if run.get("prompt_text"):
        recoverable["prompt"] = rb.digest(
            [run["prompt_text"]["prompt"], run["prompt_text"]["retry"]]
        )
    if run.get("condition_spec"):
        recoverable["condition_spec"] = rb.digest(run["condition_spec"])

    missing = dict(UNRECOVERABLE)
    if not run.get("prompt_text"):
        missing["prompt"] = "投げたプロンプト全文。保存されていない世代の結果"
    if not run.get("condition_spec"):
        missing["condition_spec"] = "各条件に何を置いたかの仕様。保存されていない世代の結果"
    if not run.get("suite"):
        missing["suite"] = "組の名前。組の仕組みより前の世代の結果"

    return {
        "stamped_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "note": (
            "この結果は入力の本文を保存していない世代のもの。下の recoverable は"
            "結果ファイルに残っていた情報から計算したものだけで、投げたデータと"
            "タスクの内容は同定できない。"
        ),
        "recoverable": recoverable,
        "unrecoverable": missing,
    }


def main():
    parser = argparse.ArgumentParser(description="既存の結果に指紋を後付けする")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに何をするか出す")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    files = sorted(RESULTS_DIR.glob("run_*.json"))
    if not files:
        raise SystemExit(f"結果ファイルが見つかりません: {RESULTS_DIR}")

    stamped = skipped = already = 0
    for path in files:
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if "fingerprint" in run:
            print(f"  そのまま: {path.name}（指紋あり）")
            already += 1
            continue
        block = backfill(run)
        if "fingerprint_backfill" in run:
            print(f"  そのまま: {path.name}（後付け済み）")
            skipped += 1
            continue
        run["fingerprint_backfill"] = block
        n_missing = len(block["unrecoverable"])
        print(f"  後付け  : {path.name}（復元不能 {n_missing} 項目）")
        if not args.dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(run, f, ensure_ascii=False, indent=2)
        stamped += 1

    print(f"\n後付け {stamped} 件 / 指紋あり {already} 件 / 済み {skipped} 件"
          + ("（--dry-run のため書き込んでいない）" if args.dry_run else ""))


if __name__ == "__main__":
    main()
