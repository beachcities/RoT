# -*- coding: utf-8 -*-
"""水準を横軸、消費を縦軸に置いた図を results/ に書き出す。

    python plot_levels.py                       # results/ の最新
    python plot_levels.py results/run_....json

縦軸は対数。傾きが変わる箇所があるかを見るためのもの。図は記述であって、
どの水準に何があるかを説明するものではない（それは conditions.json にある）。
軸ラベルは日本語フォントの有無に左右されないよう英数字にしてある。
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"


def latest_result_file():
    files = sorted(RESULTS_DIR.glob("run_*.json"))
    if not files:
        raise SystemExit(f"結果ファイルが見つかりません: {RESULTS_DIR}")
    return files[-1]


def collect(run, model):
    """条件ごとに、集計対象になった試行の総トークンと試行回数を集める。"""
    out = []
    for condition in run["conditions"]:
        rows = [
            r for r in run["results"]
            if r["model"] == model and r["condition"] == condition
            and r["status"] == "ok" and r["tokens_measured"]
        ]
        out.append({
            "name": condition,
            "tokens": [r["total_tokens"] for r in rows],
            "attempts": [r["attempts"] for r in rows],
            "successes": sum(1 for r in rows if r["success"]),
            "n": len(rows),
        })
    return out


def quantiles(values):
    values = sorted(values)
    n = len(values)
    if not n:
        return None, None, None
    def q(p):
        i = p * (n - 1)
        lo, hi = int(i), min(int(i) + 1, n - 1)
        return values[lo] + (values[hi] - values[lo]) * (i - lo)
    return q(0.25), q(0.5), q(0.75)


def draw(run, model, out_path):
    data = collect(run, model)
    x = list(range(len(data)))
    labels = [d["name"] for d in data]

    fig, axes = plt.subplots(3, 1, figsize=(11, 12), sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.4, 1.4]})

    ax = axes[0]
    for i, d in enumerate(data):
        if not d["tokens"]:
            continue
        # 個々の試行。二山になるので、点をそのまま出す。
        ax.plot([i] * len(d["tokens"]), d["tokens"], "o", color="#88aacc",
                markersize=5, alpha=0.55, zorder=2)
    med = []
    for i, d in enumerate(data):
        q1, q2, q3 = quantiles(d["tokens"])
        med.append(q2)
        if q2 is None:
            continue
        ax.vlines(i, q1, q3, color="#22406a", linewidth=6, alpha=0.35, zorder=3)
    xs = [i for i, m in enumerate(med) if m is not None]
    ax.plot(xs, [med[i] for i in xs], "-o", color="#22406a", linewidth=2,
            markersize=7, label="median", zorder=4)
    ax.set_yscale("log")
    ax.set_ylabel("total tokens per trial (log)")
    ax.grid(True, which="both", axis="y", alpha=0.25)
    ax.legend(loc="upper right")
    ax.set_title(
        f"{run.get('suite')} / {run.get('prompt_set')} / {model} / "
        f"repeats={run.get('repeats')} max_attempts={run.get('max_attempts')}"
    )

    ax = axes[1]
    rates = [d["successes"] / d["n"] if d["n"] else None for d in data]
    xs = [i for i, r in enumerate(rates) if r is not None]
    ax.plot(xs, [rates[i] * 100 for i in xs], "-o", color="#2f7a4f", linewidth=2)
    ax.set_ylim(-5, 105)
    ax.set_ylabel("solved (%)")
    ax.grid(True, axis="y", alpha=0.25)

    ax = axes[2]
    cap = run.get("max_attempts")
    att_med = [quantiles(d["attempts"])[1] for d in data]
    xs = [i for i, m in enumerate(att_med) if m is not None]
    ax.plot(xs, [att_med[i] for i in xs], "-o", color="#8a5a2b", linewidth=2,
            label="median attempts")
    if cap:
        ax.axhline(cap, color="#aa3333", linestyle="--", linewidth=1,
                   label=f"cap ({cap})")
    ax.set_ylabel("attempts")
    ax.set_xlabel("level (see conditions.json for what each one carries)")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="水準ごとの消費を図にする")
    parser.add_argument("path", nargs="?", help="結果JSON（省略時は results/ の最新）")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    path = Path(args.path) if args.path else latest_result_file()
    with open(path, encoding="utf-8") as f:
        run = json.load(f)
    if len(run.get("conditions", [])) < 3:
        raise SystemExit("条件が3つ未満です。水準ごとの図は出しません。")
    for model in run["models"]:
        out = path.with_name(f"{path.stem}_{model}.png")
        draw(run, model, out)
        print(f"saved: {out}")


if __name__ == "__main__":
    main()
