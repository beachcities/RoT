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
import statistics
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


def distribution(values):
    """1試行ごとの値の散らばり。平均だけでは分布の形が見えないため。"""
    values = sorted(values)
    n = len(values)
    empty = {"n": n, "median": None, "q1": None, "q3": None, "min": None, "max": None}
    if not n:
        return empty
    q1 = q3 = None
    if n >= 2:
        q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "n": n,
        "median": round(statistics.median(values), 4),
        "q1": None if q1 is None else round(q1, 4),
        "q3": None if q3 is None else round(q3, 4),
        "min": values[0],
        "max": values[-1],
    }


def ranges_overlap(a, b):
    """二つの分布の最小-最大が重なるか。検定ではなく、範囲を並べただけのもの。"""
    if a["min"] is None or b["min"] is None:
        return None
    return a["min"] <= b["max"] and b["min"] <= a["max"]


def summarize_condition(rows, max_attempts=None):
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
        "total_tokens_dist": distribution([]),
        "attempts_dist": distribution([]),
        "rot_per_trial_dist": distribution([]),
        # 二山を分けたもの。判定基準は success そのもの（下の注を参照）。
        "solved_tokens_dist": distribution([]),
        "unsolved_tokens_dist": distribution([]),
        "solved_attempts_dist": distribution([]),
        "unsolved_attempts_dist": distribution([]),
        # 試行回数が上限に張り付いた件数。上限で頭を打っているなら、試行回数は
        # 連続量として読めない。
        "at_cap": None,
        # タスクごとの内訳。タスクをまたいで混ぜると、難度の違う問いが1つの
        # 中央値に潰れる。
        "per_task": {},
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
            "total_tokens_dist": distribution([r["total_tokens"] for r in usable]),
            "attempts_dist": distribution([r["attempts"] for r in usable]),
            # 反復ごとの ROT。解けなかった反復は 0 になるので分布は二山になる。
            # プールした ROT（上の rot_per_1k）とは別物として読むこと。
            "rot_per_trial_dist": distribution(
                [
                    round((1.0 if r["success"] else 0.0) / r["total_tokens"] * 1000, 4)
                    for r in usable
                    if r["total_tokens"]
                ]
            ),
            # 総トークンの分布は二山になる。解けた試行は打ち切りを待たずに終わり、
            # 解けなかった試行は上限まで使う。混ぜた中央値は両者の混合比で動くので、
            # 分けたものを併記する。分ける基準は success（正答したか）そのもの。
            "solved_tokens_dist": distribution(
                [r["total_tokens"] for r in usable if r["success"]]
            ),
            "unsolved_tokens_dist": distribution(
                [r["total_tokens"] for r in usable if not r["success"]]
            ),
            "at_cap": (
                None if not max_attempts
                else sum(1 for r in usable if r["attempts"] >= max_attempts)
            ),
            "per_task": per_task_stats(usable),
            "solved_attempts_dist": distribution(
                [r["attempts"] for r in usable if r["success"]]
            ),
            "unsolved_attempts_dist": distribution(
                [r["attempts"] for r in usable if not r["success"]]
            ),
        }
    )
    return stats


def per_task_stats(usable):
    """タスクごとの正答数と消費。難度の違う問いを混ぜないために出す。"""
    out = {}
    for row in usable:
        out.setdefault(row["task_id"], []).append(row)
    return {
        task_id: {
            "used": len(rows),
            "successes": sum(1 for r in rows if r["success"]),
            "tokens": distribution([r["total_tokens"] for r in rows]),
            "attempts": distribution([r["attempts"] for r in rows]),
        }
        for task_id, rows in out.items()
    }


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

    overlap = ranges_overlap(target["total_tokens_dist"], baseline["total_tokens_dist"])
    if overlap is True:
        notes.append(
            f"総トークンの範囲が条件間で重なっている"
            f"（各 n={baseline['used']}, {target['used']}）。この反復数で見るかぎり、"
            "条件間の差はばらつきに埋もれている。検定ではない"
        )
    elif overlap is False:
        notes.append(
            f"総トークンの範囲は条件間で重なっていない"
            f"（各 n={baseline['used']}, {target['used']}）。範囲を並べただけであり、"
            "検定ではない"
        )

    return {
        "available": True,
        "baseline": BASELINE_CONDITION,
        "target": TARGET_CONDITION,
        "rot_ratio": rot_ratio,
        "total_tokens_ratio": ratio(target["total_tokens"], baseline["total_tokens"]),
        "prompt_tokens_ratio": ratio(target["prompt_tokens"], baseline["prompt_tokens"]),
        "completion_tokens_ratio": ratio(target["completion_tokens"], baseline["completion_tokens"]),
        "attempts_ratio": ratio(target["attempts_mean"], baseline["attempts_mean"]),
        "total_tokens_median_ratio": ratio(
            target["total_tokens_dist"]["median"], baseline["total_tokens_dist"]["median"]
        ),
        "total_tokens_range_overlap": ranges_overlap(
            target["total_tokens_dist"], baseline["total_tokens_dist"]
        ),
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
    task_ids = []
    for r in results:
        if r.get("task_id") not in task_ids:
            task_ids.append(r.get("task_id"))

    per_model = {}
    for model in models:
        by_condition = {}
        for condition in conditions:
            rows = [r for r in results if r["model"] == model and r["condition"] == condition]
            by_condition[condition] = summarize_condition(rows, run.get("max_attempts"))
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
        "tasks": task_ids,
        "suite": run.get("suite"),
        "prompt_set": run.get("prompt_set"),
        "max_attempts": run.get("max_attempts"),
        "condition_spec": run.get("condition_spec"),
        "repeats": run.get("repeats"),
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


def wrap(text, width=72, indent=""):
    """表示幅で折り返す。全角が混ざるので textwrap は使えない。"""
    lines = []
    current = ""
    for char in text:
        if display_width(current) + display_width(char) > width and current:
            lines.append(indent + current)
            current = ""
        current += char
    if current:
        lines.append(indent + current)
    return lines


def span(low, high, digits=None):
    if low is None or high is None:
        return "n/a"
    return f"{cell(low, digits)}-{cell(high, digits)}"


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

SPREAD_COLS = [
    ("condition", 18),
    ("正答/n", 9),
    ("総token中央", 12),
    ("Q1-Q3", 14),
    ("最小-最大", 14),
    ("ROT/1k中央", 12),
    ("ROT/1k範囲", 16),
]

LEVEL_COLS = [
    ("水準", 18),
    ("正答/n", 9),
    ("総token中央", 12),
    ("Q1-Q3", 14),
    ("最小-最大", 14),
    ("試行中央", 10),
    ("上限到達", 10),
    ("ROT/1k", 9),
    ("中央値比", 10),
]

SPLIT_COLS = [
    ("condition", 18),
    ("内訳", 10),
    ("件数", 6),
    ("総token中央", 12),
    ("Q1-Q3", 14),
    ("最小-最大", 14),
    ("試行中央", 10),
]

RATIO_LABELS = [
    ("rot_ratio", "ROT/1k"),
    ("total_tokens_ratio", "総トークン"),
    ("total_tokens_median_ratio", "総トークン中央値"),
    ("prompt_tokens_ratio", "入力トークン"),
    ("completion_tokens_ratio", "生成トークン"),
    ("attempts_ratio", "試行回数"),
]


def render(summary):
    lines = []
    lines.append("=" * 78)
    lines.append("集計（同一モデル内での、データ条件による比較）")
    if summary.get("suite"):
        label = f"組: {summary['suite']}"
        if summary.get("prompt_set"):
            label += f"  /  プロンプト: {summary['prompt_set']}"
        lines.append(label + "  （どちらかが違えば数値は比較できない）")
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

        lines.append("")
        lines.append("  反復にわたるばらつき（値は1試行あたり）")
        header = row(SPREAD_COLS)
        lines.append(header)
        lines.append("-" * display_width(header))
        widths = [w for _, w in SPREAD_COLS]
        for condition, st in entry["per_condition"].items():
            tok = st["total_tokens_dist"]
            rot = st["rot_per_trial_dist"]
            values = [
                condition,
                "n/a" if st["successes"] is None else f"{st['successes']}/{st['used']}",
                cell(tok["median"], 0),
                span(tok["q1"], tok["q3"], 0),
                span(tok["min"], tok["max"], 0),
                cell(rot["median"], 4),
                span(rot["min"], rot["max"], 4),
            ]
            lines.append(row(zip(values, widths)))

        lines.append("")
        lines.append("  解けた試行と解けなかった試行を分けたもの（総トークンは二山になる）")
        header = row(SPLIT_COLS)
        lines.append(header)
        lines.append("-" * display_width(header))
        widths = [w for _, w in SPLIT_COLS]
        for condition, st in entry["per_condition"].items():
            for label, tok_key, att_key in (
                ("解けた", "solved_tokens_dist", "solved_attempts_dist"),
                ("解けず", "unsolved_tokens_dist", "unsolved_attempts_dist"),
            ):
                tok = st[tok_key]
                att = st[att_key]
                if not tok["n"]:
                    continue
                lines.append(
                    row(zip([condition, label, tok["n"], cell(tok["median"], 0),
                             span(tok["q1"], tok["q3"], 0), span(tok["min"], tok["max"], 0),
                             "n/a" if att["median"] is None else f"{float(att['median']):.1f}"],
                            widths))
                )

        tasks = summary.get("tasks") or []
        if len(tasks) > 1:
            for title, pick in (
                ("正答数（タスク別）", lambda st: (
                    "-" if not st else f"{st['successes']}/{st['used']}")),
                ("総トークン中央値（タスク別）", lambda st: (
                    "-" if not st else cell(st["tokens"]["median"], 0))),
            ):
                lines.append("")
                lines.append(f"  {title}")
                cols = [("水準", 18)] + [(t, 12) for t in tasks]
                header = row(cols)
                lines.append(header)
                lines.append("-" * display_width(header))
                widths = [w for _, w in cols]
                for condition, st in entry["per_condition"].items():
                    values = [condition] + [
                        pick(st["per_task"].get(task_id)) for task_id in tasks
                    ]
                    lines.append(row(zip(values, widths)))

        if len(entry["per_condition"]) > 2:
            lines.append("")
            cap = summary.get("max_attempts")
            lines.append(
                "  水準ごとの消費（中央値比は先頭の水準を1としたもの"
                + (f"。上限到達は試行が {cap} 回に達した件数" if cap else "")
                + "）"
            )
            header = row(LEVEL_COLS)
            lines.append(header)
            lines.append("-" * display_width(header))
            widths = [w for _, w in LEVEL_COLS]
            base = None
            for condition, st in entry["per_condition"].items():
                tok = st["total_tokens_dist"]
                att = st["attempts_dist"]
                if base is None:
                    base = tok["median"]
                lines.append(
                    row(zip([
                        condition,
                        "n/a" if st["successes"] is None else f"{st['successes']}/{st['used']}",
                        cell(tok["median"], 0),
                        span(tok["q1"], tok["q3"], 0),
                        span(tok["min"], tok["max"], 0),
                        "n/a" if att["median"] is None else f"{float(att['median']):.1f}",
                        cell(st["at_cap"]),
                        cell(st["rot_per_1k"], 4),
                        cell(ratio(tok["median"], base), 3),
                    ], widths))
                )

        comparison = entry.get("comparison")
        if not comparison:
            continue
        lines.append("")
        if not comparison["available"]:
            for note in comparison["notes"]:
                lines.extend(wrap(note, width=70, indent="  * "))
            continue
        lines.append(
            f"  条件比 {comparison['target']} / {comparison['baseline']}"
            "  （1.0 が「差なし」。1より大きければ左が大きい）"
        )
        for key, label in RATIO_LABELS:
            lines.append("    " + pad(label, 18) + cell(comparison[key], 4))
        delta = comparison["success_rate_delta"]
        lines.append("    " + pad("正答率の差", 18) + f"{delta * 100:+.1f} ポイント")
        for note in comparison["notes"]:
            wrapped = wrap(note, width=68)
            lines.append(f"    * {wrapped[0]}")
            lines.extend(f"      {line}" for line in wrapped[1:])

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
    lines.append("  * 二山を分ける基準は success（正答したか）そのもの。解けた試行は打ち切りを")
    lines.append("    待たずに終わり、解けなかった試行は上限まで使うため、混ぜた中央値は")
    lines.append("    両者の混合比で動く。混合比は反復ごとに変わる。")
    lines.append("  * ROT/1k はプール算出（正答数 / 総トークン × 1000）。ばらつき表の")
    lines.append("    ROT/1k は反復ごとの値で、解けなかった反復は 0 になるため二山になる。")
    lines.append("    両者は別物として読むこと。")
    if summary.get("repeats"):
        note = (
            f"反復 {summary['repeats']} 回は暫定値。差の大きさがばらつきに対して"
            "どの程度かを見て、必要なら増やす前提の数字。"
        )
        wrapped = wrap(note, width=70)
        lines.append(f"  * {wrapped[0]}")
        lines.extend(f"    {line}" for line in wrapped[1:])
    if len(summary.get("tasks") or []) == 1:
        lines.append("  * タスクが1件しかないため、ばらつきは単一タスクの反復のみから来ている。")
        lines.append("    タスク間の差は評価できない。")
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
