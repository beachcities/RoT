"""実行結果を、同一モデル内のデータ条件比較として読める形にまとめる。

run_benchmark.py から呼ばれるほか、保存済みの結果に対して単体でも走る。

    python summarize.py                       # results/ の最新を集計
    python summarize.py results/run_....json  # ファイルを指定

集計の方針:

* ROT は試行ごとの平均ではなく、条件ごとにプールして出す。
  ROT = 正答数 / その条件で投じた総トークン数 x 1000
  試論の定義（分母は投じた総トークン、探索で捨てた分を含む）をそのまま条件
  単位に上げたもの。試行ごとの ROT を平均すると、少ないトークンで解けた試行の
  影響が実際より大きく出る。

* 入力トークンと生成トークンを分けて出す。自己記述的なデータは記述が増える分
  だけ入力が長くなるので、総トークンだけを見ると、生成側で何が起きたのかが
  入力の増分に埋もれる。どちらの向きに動いたかは実行してみるまで分からない。

* モデル間で並べるのは比だけにする。トークナイザが違えば総トークンの絶対値は
  比較できない（試論 3節の留保）。

* status=error の試行と、usage が取れずトークンを計測できていない試行は集計
  から除外し、除外した数を明示する。
"""

import argparse
import json
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

BASELINE_CONDITION = "raw"
TARGET_CONDITION = "self_descriptive"


def ratio(target, baseline):
    """target / baseline。比が定義できなければ None。"""
    if target is None or baseline is None:
        return None
    if baseline == 0:
        return None
    return round(target / baseline, 4)


def summarize_condition(rows):
    """1モデル1条件ぶんの行をまとめる。"""
    usable = [r for r in rows if r.get("status") == "ok" and r.get("tokens_measured")]
    excluded = len(rows) - len(usable)

    stats = {
        "trials": len(rows),
        "used": len(usable),
        "excluded": excluded,
        "successes": None,
        "success_rate": None,
        "attempts_mean": None,
        "prompt_tokens": None,
        "reasoning_tokens": None,
        "output_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "tokens_per_trial": None,
        "rot_per_1k": None,
    }
    if not usable:
        return stats

    successes = sum(1 for r in usable if r["success"])
    total_tokens = sum(r["total_tokens"] for r in usable)
    prompt_tokens = sum(r["prompt_tokens"] for r in usable)
    completion_tokens = sum(r["completion_tokens"] for r in usable)

    # 内訳は全試行で揃っているときだけ出す。欠けた試行を 0 として足すと、
    # 取れなかったことと 0 だったことが区別できなくなる。
    reasoning_tokens = None
    output_tokens = None
    if all(r["reasoning_tokens"] is not None for r in usable):
        reasoning_tokens = sum(r["reasoning_tokens"] for r in usable)
        output_tokens = sum(r["output_tokens"] for r in usable)

    stats.update(
        {
            "successes": successes,
            "success_rate": round(successes / len(usable), 4),
            "attempts_mean": round(sum(r["attempts"] for r in usable) / len(usable), 3),
            "prompt_tokens": prompt_tokens,
            "reasoning_tokens": reasoning_tokens,
            "output_tokens": output_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokens_per_trial": round(total_tokens / len(usable), 1),
            "rot_per_1k": round(successes / total_tokens * 1000, 4) if total_tokens else None,
        }
    )
    return stats


def compare(target, baseline):
    """同一モデル内での条件比較。self_descriptive / raw の比を出す。"""
    notes = []
    missing = [
        name
        for name, stats in ((BASELINE_CONDITION, baseline), (TARGET_CONDITION, target))
        if not stats["used"]
    ]
    if missing:
        return {
            "available": False,
            "notes": [f"集計できる試行が無いため条件比を出せない（{', '.join(missing)}）"],
        }

    rot_ratio = ratio(target["rot_per_1k"], baseline["rot_per_1k"])
    if rot_ratio is None and baseline["rot_per_1k"] == 0:
        notes.append(f"{BASELINE_CONDITION} 側の正答が0のため ROT の比は定義できない")

    if target["success_rate"] != baseline["success_rate"]:
        notes.append(
            "正答率が条件間で異なる。ROT の比には正答率の差とトークン量の差が"
            "両方入っているので、分けて読むこと"
        )
    if baseline["used"] < 3 or target["used"] < 3:
        notes.append("試行数が少ない。比のばらつきを評価できる規模ではない")

    return {
        "available": True,
        "baseline": BASELINE_CONDITION,
        "target": TARGET_CONDITION,
        "rot_ratio": rot_ratio,
        "total_tokens_ratio": ratio(target["total_tokens"], baseline["total_tokens"]),
        "prompt_tokens_ratio": ratio(target["prompt_tokens"], baseline["prompt_tokens"]),
        "completion_tokens_ratio": ratio(target["completion_tokens"], baseline["completion_tokens"]),
        "attempts_ratio": ratio(target["attempts_mean"], baseline["attempts_mean"]),
        "success_rate_delta": round(target["success_rate"] - baseline["success_rate"], 4),
        "notes": notes,
    }


def summarize(run):
    """実行結果全体を集計する。run は run_benchmark.main() が返す dict。"""
    results = run.get("results", [])
    models = []
    for r in results:
        if r["model"] not in models:
            models.append(r["model"])
    conditions = run.get("conditions") or [BASELINE_CONDITION, TARGET_CONDITION]

    per_model = {}
    for model in models:
        by_condition = {}
        for condition in conditions:
            rows = [r for r in results if r["model"] == model and r["condition"] == condition]
            by_condition[condition] = summarize_condition(rows)
        entry = {"per_condition": by_condition}
        if BASELINE_CONDITION in by_condition and TARGET_CONDITION in by_condition:
            entry["comparison"] = compare(
                by_condition[TARGET_CONDITION], by_condition[BASELINE_CONDITION]
            )
        per_model[model] = entry

    excluded = sum(
        c["excluded"] for m in per_model.values() for c in m["per_condition"].values()
    )
    return {
        "models": models,
        "conditions": conditions,
        "baseline_condition": BASELINE_CONDITION,
        "target_condition": TARGET_CONDITION,
        "excluded_trials": excluded,
        "per_model": per_model,
    }


# --- 表示 ----------------------------------------------------------------


def display_width(text):
    """全角を2桁として数える。桁を揃えるのに f-string の幅指定は使えない。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text, width):
    text = str(text)
    return text + " " * max(1, width - display_width(text))


def row(cells):
    return "".join(pad(text, width) for text, width in cells).rstrip()


def cell(value, digits=None):
    if value is None:
        return "n/a"
    if digits is not None and isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value):
    return "n/a" if value is None else f"{value * 100:.1f}%"


CONDITION_COLS = [
    ("condition", 18),
    ("試行", 6),
    ("正答", 6),
    ("正答率", 8),
    ("平均試行", 9),
    ("入力", 9),
    ("CoT", 9),
    ("出力", 9),
    ("総token", 9),
    ("ROT/1k", 9),
]

RATIO_LABELS = [
    ("rot_ratio", "ROT/1k"),
    ("total_tokens_ratio", "総トークン"),
    ("prompt_tokens_ratio", "入力トークン"),
    ("completion_tokens_ratio", "生成トークン"),
    ("attempts_ratio", "試行回数"),
]


def render(summary):
    lines = []
    lines.append("=" * 78)
    lines.append("集計（同一モデル内での、データ条件による比較）")
    lines.append("=" * 78)

    for model, entry in summary["per_model"].items():
        lines.append("")
        lines.append(f"[{model}]")
        header = row(CONDITION_COLS)
        lines.append(header)
        lines.append("-" * display_width(header))
        widths = [w for _, w in CONDITION_COLS]
        for condition, st in entry["per_condition"].items():
            note = f"  (除外 {st['excluded']})" if st["excluded"] else ""
            values = [
                condition,
                st["trials"],
                cell(st["successes"]),
                pct(st["success_rate"]),
                cell(st["attempts_mean"], 2),
                cell(st["prompt_tokens"]),
                cell(st["reasoning_tokens"]),
                cell(st["output_tokens"]),
                cell(st["total_tokens"]),
                cell(st["rot_per_1k"], 4),
            ]
            lines.append(row(zip(values, widths)) + note)

        comparison = entry.get("comparison")
        if not comparison:
            continue
        lines.append("")
        if not comparison["available"]:
            for note in comparison["notes"]:
                lines.append(f"  * {note}")
            continue
        lines.append(
            f"  条件比 {comparison['target']} / {comparison['baseline']}"
            "  （1.0 が「差なし」。1より大きければ左が大きい）"
        )
        for key, label in RATIO_LABELS:
            lines.append("    " + pad(label, 16) + cell(comparison[key], 4))
        delta = comparison["success_rate_delta"]
        lines.append("    " + pad("正答率の差", 16) + f"{delta * 100:+.1f} ポイント")
        for note in comparison["notes"]:
            lines.append(f"    * {note}")

    ratios = [
        (m, e["comparison"])
        for m, e in summary["per_model"].items()
        if e.get("comparison", {}).get("available")
    ]
    if len(ratios) > 1:
        lines.append("")
        lines.append("-" * 78)
        lines.append(
            "モデル間で並べてよいのは比だけ"
            "（トークナイザが違うため総トークンの絶対値は比較できない）"
        )
        cross_cols = [("model", 24), ("ROT比", 10), ("総token比", 12),
                      ("生成token比", 14), ("試行比", 9), ("正答率差", 10)]
        header = row(cross_cols)
        lines.append(header)
        lines.append("-" * display_width(header))
        widths = [w for _, w in cross_cols]
        for model, c in ratios:
            values = [
                model,
                cell(c["rot_ratio"], 4),
                cell(c["total_tokens_ratio"], 4),
                cell(c["completion_tokens_ratio"], 4),
                cell(c["attempts_ratio"], 4),
                f"{c['success_rate_delta'] * 100:+.1f}pt",
            ]
            lines.append(row(zip(values, widths)))

    lines.append("")
    lines.append("-" * 78)
    lines.append("読み方の留保")
    lines.append("  * 分子は正答/誤答の二値。試論が挙げた成果の測り方のいずれでもない。")
    lines.append("  * 総トークンの絶対値はトークナイザ依存。モデル間で比べられるのは比のみ。")
    lines.append("  * 自己記述的なデータは記述が増える分だけ入力が長くなる。総トークンの")
    lines.append("    比を見るときは、入力と生成のどちらが動いたのかを分けて見ること。")
    lines.append("  * CoT が n/a のモデルは内訳が取れていない。総量のみの比較になる。")
    if summary["excluded_trials"]:
        lines.append(
            f"  * {summary['excluded_trials']} 件を集計から除外した"
            "（通信エラー、または usage が返らずトークン未計測）。"
        )
    return "\n".join(lines)


def latest_result_file():
    files = sorted(RESULTS_DIR.glob("run_*.json"))
    if not files:
        raise SystemExit(f"結果ファイルが見つかりません: {RESULTS_DIR}")
    return files[-1]


def main():
    parser = argparse.ArgumentParser(description="ROT benchmark result summarizer")
    parser.add_argument("path", nargs="?", help="結果JSON（省略時は results/ の最新）")
    parser.add_argument("--json", action="store_true", help="集計結果をJSONで出す")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    path = Path(args.path) if args.path else latest_result_file()
    with open(path, encoding="utf-8") as f:
        run = json.load(f)

    summary = summarize(run)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"source: {path}")
        if run.get("mock"):
            print("※ このファイルは --mock による実行結果です。ダミー応答であり実測ではありません。")
        print()
        print(render(summary))


if __name__ == "__main__":
    main()
