# -*- coding: utf-8 -*-
"""公開する結果を results/reference/ に書き出す。

    python export_reference.py [--dry-run]

方針（`analysis/RESULTS_PUBLICATION.md` の案F）:

* **参照点となるランは応答本文ごと**置く。再採点も抽出規則の検証もできる形にする。
* **公開対象の全ランは、試行ごとの数値だけ**を1つのCSVにまとめる。
* **台帳**（RUNS.md）を添える。どのランが何のための実行かを人が読める形で残す。
* それ以外の作業中のランは `.gitignore` のまま出さない。

公開対象にするのは、**入力を同定できるラン**だけである。`inputs` を保存していない
世代の結果は、結果ファイルからは何を投げたのか分からない。再現できない数値が
出典つきで引用されうるので出さない。モック実行も出さない（実測と誤読されるため）。
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
OUT_DIR = RESULTS_DIR / "reference"
RUNS_SUBDIR = Path("runs")

# 参照点。稿の第5節が引く数値はこの3本から出ている。
# 同一の入力・プロンプト・サンプリングで、モデルだけを変えたもの。
REFERENCE = [
    "run_20260820T135439Z.json",
    "run_20260820T143501Z.json",
    "run_20260820T154458Z.json",
    # ローカルで回した推論モデル。応答本文に加えて中間推論のテキストが入る。
    "run_20260823T124213Z.json",
    # オープンウェイトの系統を一つ。thinking の on/off を同じ入力で比べたもの。
    "run_20260824T061642Z.json",
    "run_20260824T034646Z.json",
]

# 台帳の注記。機械で書けないので手で書く。キーはファイル名。
NOTES = {
    "run_20260820T014810Z.json": "スモークテスト。gpt-4.1-mini の疎通とサンプリング設定の受理を確認",
    "run_20260820T014920Z.json": "スモークテスト。gpt-5.4 の疎通とサンプリング設定の受理を確認",
    "run_20260820T015043Z.json": "**破棄**。採点器の欠陥（空白除去で数値が連結）を含む。gpt-5.4 で正誤の反転298件",
    "run_20260820T022326Z.json": "**破棄**。同上。gpt-4.1-mini で正誤の反転66件",
    "run_20260820T030616Z.json": "**破棄**。同上。gpt-4o-mini では反転0件。欠陥がモデル依存に働いた証拠",
    "run_20260820T041927Z.json": "採点修正後。6タスク版。task_06 に消去法の逃げ道が残っていた",
    "run_20260820T043012Z.json": "同上。gpt-4.1-mini",
    "run_20260820T050519Z.json": "同上。gpt-4o-mini",
    "run_20260820T073809Z.json": "逃げ道を一度塞いだ版（13レコード）。並び順と所属企業数の手がかりが残っていた",
    "run_20260820T081710Z.json": "同上。gpt-4.1-mini",
    "run_20260820T092002Z.json": "gpt-5.4 の費用を見積もるための小規模実行（2水準×1タスク×2反復）",
    "run_20260820T092139Z.json": "**未完**。APIのクレジット枯渇により100実行中61件がエラー",
    "run_20260820T123300Z.json": "上記の再実行。13レコード版での gpt-5.4",
    "run_20260820T135439Z.json": "**参照点**。識別子を7つ潰した版（17レコード）。gpt-4o-mini",
    "run_20260820T143501Z.json": "**参照点**。同上。gpt-4.1-mini",
    "run_20260820T154227Z.json": "l9 の追試（l9 のみ、10反復）。以前の版で観測された崩れが再現するかを見たもの",
    "run_20260820T154458Z.json": "**参照点**。同上。gpt-5.4",
    "run_20260823T124213Z.json": "**参照点**。同じ入力を Colab の A100 で回した "
                                 "allenai/Olmo-3-7B-Think（vLLM）。"
                                 "**中間推論のテキストが入る唯一のラン**。"
                                 "REPEATS=1、生成上限 32,768",
    "run_20260824T061642Z.json": "**参照点**。Qwen/Qwen3.5-9B（vLLM、Colab CLI 経路）を "
                                 "**thinking on** で。**オープンウェイトで学習データは非公開**、"
                                 "OSAID は満たさない。入力は OLMo と同一",
    "run_20260824T034646Z.json": "**参照点**。同じモデル・同じ入力を **thinking off** で"
                                 "（`enable_thinking: false`）。on との差が直接取れる。"
                                 "文脈長超過で4試行がエラー",
}

TRIAL_COLUMNS = [
    "run_at", "model", "response_model", "system_fingerprint", "suite", "prompt_set",
    "fingerprint_inputs", "condition", "task_id", "repeat", "status", "success",
    "attempts", "at_cap", "finish_reason", "prompt_tokens", "reasoning_tokens",
    "output_tokens", "completion_tokens", "total_tokens", "rot_per_1k", "latency_sec",
]


def publishable(run):
    """入力を同定できる実測ランだけを公開対象にする。"""
    return bool(run.get("fingerprint")) and not run.get("mock")


def load_runs():
    runs = []
    for path in sorted(RESULTS_DIR.glob("run_*.json")):
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if publishable(run):
            runs.append((path, run))
    return runs


def trial_rows(run):
    cap = run.get("max_attempts")
    for r in run["results"]:
        yield {
            "run_at": run["run_at"],
            "model": r["model"],
            "response_model": r.get("response_model"),
            "system_fingerprint": r.get("system_fingerprint"),
            "suite": run.get("suite"),
            "prompt_set": run.get("prompt_set"),
            "fingerprint_inputs": run["fingerprint"].get("inputs"),
            "condition": r["condition"],
            "task_id": r["task_id"],
            "repeat": r.get("repeat"),
            "status": r["status"],
            "success": r["success"],
            "attempts": r["attempts"],
            "at_cap": bool(cap) and r["attempts"] >= cap,
            "finish_reason": r.get("finish_reason"),
            "prompt_tokens": r["prompt_tokens"],
            "reasoning_tokens": r["reasoning_tokens"],
            "output_tokens": r["output_tokens"],
            "completion_tokens": r["completion_tokens"],
            "total_tokens": r["total_tokens"],
            "rot_per_1k": r["rot_per_1k"],
            "latency_sec": r["latency_sec"],
        }


def render_ledger(runs):
    lines = [
        "# 公開しているランの台帳",
        "",
        "`export_reference.py` が生成する。注記は同スクリプトの `NOTES` にある。",
        "",
        "**入力を同定できるランだけを載せている。** `inputs`（タスクと各条件のデータ本文）を",
        "保存していない世代の結果は、結果ファイルから何を投げたのかが分からないため、",
        "公開対象から外してある。モック実行も載せていない。",
        "",
        "`fingerprint.inputs` が同じランは、同じ入力を投げている。",
        "",
        "**run_at がリンクになっているランは、`runs/` に個別の記録がある**"
        "（実行の素性・経路・集計の出力・そのランに固有の留保）。",
        "全ランに共通する読み方の留保は [READING.md](READING.md) にある。",
        "",
        "| run_at | モデル | 組 | 水準 | タスク | 反復 | 試行上限 | レコード | inputs | 何のための実行か |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for path, run in runs:
        inputs = run.get("inputs") or {}
        conditions = inputs.get("conditions") or {}
        first = next(iter(conditions.values()), None)
        records = len(first["records"]) if isinstance(first, dict) and "records" in first else (
            len(first) if isinstance(first, list) else "?")
        note = NOTES.get(path.name, "")
        record = RUNS_SUBDIR / f"{run['run_at']}.md"
        link = (f"[`{run['run_at']}`](runs/{run['run_at']}.md)"
                if (OUT_DIR / record).is_file() else f"`{run['run_at']}`")
        lines.append(
            f"| {link} | {', '.join(run['models'])} | {run.get('suite')} | "
            f"{len(run.get('conditions') or [])} | {len(inputs.get('tasks') or [])} | "
            f"{run.get('repeats')} | {run.get('max_attempts')} | {records} | "
            f"`{run['fingerprint'].get('inputs')}` | {note} |"
        )
    lines += [
        "",
        "## 応答本文まで置いてあるラン",
        "",
        "`reference/` に結果JSONをそのまま置いてあるのは次の3本。同一の入力・プロンプト・",
        "サンプリングでモデルだけを変えたもので、稿の第5節が引く数値はここから出ている。",
        "",
    ]
    for name in REFERENCE:
        lines.append(f"* `{name}`")
    lines += [
        "",
        "他のランは `trials.csv` に試行ごとの数値だけを収めてある。応答本文は入っていないので、",
        "採点し直すことはできない。",
        "",
        "## 収録している列",
        "",
        "`trials.csv` は1行が1試行（1セル1反復）。`attempts` はその試行で要求した回数、",
        "`at_cap` は試行上限に達したかどうか。`total_tokens` は失敗した試行の分を含む累計。",
        "`status` が `ok` 以外の行と、`total_tokens` が計測できなかった行は、集計から除外される。",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="公開する結果を書き出す")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに内容を出す")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    runs = load_runs()
    if not runs:
        raise SystemExit("公開対象のランがありません（inputs を持つ実測ランが無い）")

    missing = [n for n in REFERENCE if not (RESULTS_DIR / n).is_file()]
    if missing:
        raise SystemExit(f"参照点のランが見つかりません: {', '.join(missing)}")

    rows = [row for _, run in runs for row in trial_rows(run)]
    print(f"公開対象 {len(runs)} ラン / 試行 {len(rows)} 行")
    for name in REFERENCE:
        print(f"  応答本文ごと: {name} ({(RESULTS_DIR / name).stat().st_size / 1e6:.2f} MB)")
    if args.dry_run:
        print("(--dry-run のため書き込んでいない)")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in REFERENCE:
        shutil.copy2(RESULTS_DIR / name, OUT_DIR / name)
    with open(OUT_DIR / "trials.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRIAL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    (OUT_DIR / "RUNS.md").write_text(render_ledger(runs), encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT_DIR.iterdir() if p.is_file())
    print(f"書き出した: {OUT_DIR}  合計 {total / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
