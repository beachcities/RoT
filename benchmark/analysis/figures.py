"""総トークンの分布を、要約する前にそのまま見るための図を出す。

方針:
- 点は間引かない。全試行を打つ。
- 横軸（総トークン）は常に対数。
- ヒストグラムはビン幅を1つに決めない。頻度軸も線形と対数を両方出す。
- 群の数を仮定した当てはめ（混合分布・クラスタリング）は一切しない。
図中のラベルはASCIIのみ（日本語フォント依存を避けるため）。
"""

import os
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from dataset import load_runs, levels_in, OUT_DIR

FIG_DIR = os.path.join(OUT_DIR, "figures")
HIST_DIR = os.path.join(FIG_DIR, "hist")
TASK_MARKERS = {"task_01": "o", "task_02": "s", "task_03": "^"}
TASK_COLORS = {"task_01": "#1f77b4", "task_02": "#d62728", "task_03": "#2ca02c"}


def swarm_offsets(xs, width=0.34, dex=0.035):
    """対数軸上で近い点を縦にずらす（重なりを隠さないため）。決定的。"""
    xs = np.asarray(xs, dtype=float)
    if len(xs) == 0:
        return np.zeros(0)
    lx = np.log10(np.maximum(xs, 1.0))
    order = np.argsort(lx, kind="stable")
    offs = np.zeros(len(xs))
    placed = []  # (lx, off)
    for i in order:
        step = 0
        while True:
            chosen = None
            for cand in ([0.0] if step == 0 else [step, -step]):
                off = cand * (width / 6.0)
                if abs(off) > width:
                    continue
                if all(abs(lx[i] - px) > dex or abs(off - po) > 1e-9 for px, po in placed):
                    chosen = off
                    break
            if chosen is not None:
                offs[i] = chosen
                placed.append((lx[i], chosen))
                break
            step += 1
            if step > 40:
                offs[i] = 0.0
                placed.append((lx[i], 0.0))
                break
    return offs


def _rows_for(rows, run_id):
    return [r for r in rows if r["run_id"] == run_id and r["total_tokens"]]


def _setup_axis(ax, conds, title, xlabel="total tokens per trial (log)"):
    ax.set_yticks(range(len(conds)))
    ax.set_yticklabels(conds, fontsize=8)
    ax.set_ylim(-0.7, len(conds) - 0.3)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel(xlabel, fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(axis="x", which="both", alpha=0.25, lw=0.5)
    ax.tick_params(labelsize=8)


def _panel_grid(runs, rows, figsize_per=(6.2, 0.45)):
    """runごとに1パネル。高さは水準数に比例させる。"""
    ns = [len(levels_in(rows, m["run_id"])) for m in runs]
    fig, axes = plt.subplots(
        len(runs), 1,
        figsize=(figsize_per[0], sum(max(n, 2) * figsize_per[1] + 1.1 for n in ns)),
        gridspec_kw={"height_ratios": [max(n, 2) for n in ns]},
    )
    if len(runs) == 1:
        axes = [axes]
    return fig, list(axes)


def fig_strip_raw(runs, rows):
    fig, axes = _panel_grid(runs, rows)
    for ax, meta in zip(axes, runs):
        conds = levels_in(rows, meta["run_id"])
        rr = _rows_for(rows, meta["run_id"])
        for i, c in enumerate(conds):
            sub = [r for r in rr if r["condition"] == c]
            xs = [r["total_tokens"] for r in sub]
            ax.scatter(xs, i + swarm_offsets(xs), s=16, c="#222222", alpha=0.8, lw=0)
        _setup_axis(ax, conds, "run %s  (repeats=%s, max_attempts=%s, n=%d)"
                    % (meta["run_id"], meta["repeats"], meta["max_attempts"], len(rr)))
    fig.suptitle("Raw total-token points per level (no summary statistics)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(os.path.join(FIG_DIR, "fig01_strip_raw.png"), dpi=160)
    plt.close(fig)


def fig_strip_by_attempts(runs, rows):
    fig, axes = _panel_grid(runs, rows)
    vmax = max(r["attempts"] for r in rows if r["attempts"])
    cmap = plt.get_cmap("viridis")
    norm = matplotlib.colors.Normalize(vmin=1, vmax=vmax)
    sc = None
    for ax, meta in zip(axes, runs):
        conds = levels_in(rows, meta["run_id"])
        rr = _rows_for(rows, meta["run_id"])
        for i, c in enumerate(conds):
            sub = [r for r in rr if r["condition"] == c]
            xs = [r["total_tokens"] for r in sub]
            sc = ax.scatter(xs, i + swarm_offsets(xs), s=22,
                            c=[r["attempts"] for r in sub], cmap=cmap, norm=norm, lw=0)
        _setup_axis(ax, conds, "run %s  (color = attempts used, cap=%s)"
                    % (meta["run_id"], meta["max_attempts"]))
    fig.colorbar(sc, ax=axes, fraction=0.03, pad=0.02, label="attempts")
    fig.suptitle("Total tokens per trial, colored by number of attempts", fontsize=10)
    fig.savefig(os.path.join(FIG_DIR, "fig02_strip_by_attempts.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_strip_by_success(runs, rows):
    fig, axes = _panel_grid(runs, rows)
    for ax, meta in zip(axes, runs):
        conds = levels_in(rows, meta["run_id"])
        rr = _rows_for(rows, meta["run_id"])
        for i, c in enumerate(conds):
            sub = [r for r in rr if r["condition"] == c]
            xs = [r["total_tokens"] for r in sub]
            off = i + swarm_offsets(xs)
            ok = [j for j, r in enumerate(sub) if r["success"]]
            ng = [j for j, r in enumerate(sub) if not r["success"]]
            ax.scatter([xs[j] for j in ok], [off[j] for j in ok], s=20,
                       c="#1a7f37", marker="o", lw=0, alpha=0.85)
            ax.scatter([xs[j] for j in ng], [off[j] for j in ng], s=34,
                       c="#cf222e", marker="x", lw=1.2)
        _setup_axis(ax, conds, "run %s" % meta["run_id"])
    axes[0].legend(
        handles=[Line2D([], [], ls="", marker="o", color="#1a7f37", label="correct"),
                 Line2D([], [], ls="", marker="x", color="#cf222e", label="not correct")],
        fontsize=7, loc="lower right")
    fig.suptitle("Total tokens per trial, marked by whether the trial ever answered correctly", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(os.path.join(FIG_DIR, "fig03_strip_by_success.png"), dpi=160)
    plt.close(fig)


def fig_strip_by_task(runs, rows):
    fig, axes = _panel_grid(runs, rows)
    for ax, meta in zip(axes, runs):
        conds = levels_in(rows, meta["run_id"])
        rr = _rows_for(rows, meta["run_id"])
        for i, c in enumerate(conds):
            sub = [r for r in rr if r["condition"] == c]
            xs = [r["total_tokens"] for r in sub]
            off = i + swarm_offsets(xs)
            for t in sorted(TASK_MARKERS):
                idx = [j for j, r in enumerate(sub) if r["task_id"] == t]
                if not idx:
                    continue
                ax.scatter([xs[j] for j in idx], [off[j] for j in idx], s=20,
                           marker=TASK_MARKERS[t], c=TASK_COLORS[t], lw=0, alpha=0.85)
        _setup_axis(ax, conds, "run %s" % meta["run_id"])
    axes[0].legend(
        handles=[Line2D([], [], ls="", marker=TASK_MARKERS[t], color=TASK_COLORS[t], label=t)
                 for t in sorted(TASK_MARKERS)],
        fontsize=7, loc="lower right")
    fig.suptitle("Total tokens per trial, split by task", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.985])
    fig.savefig(os.path.join(FIG_DIR, "fig04_strip_by_task.png"), dpi=160)
    plt.close(fig)


def fig_hist_binwidths(runs, rows):
    """水準ごとに、ビン幅4通り x 頻度軸2通りの8パネル。山の数がビン幅で変わるかを見る。"""
    widths = [0.05, 0.10, 0.20, 0.40]  # log10 単位（dex）
    made = []
    for meta in runs:
        rr = _rows_for(rows, meta["run_id"])
        lo = math.log10(min(r["total_tokens"] for r in rr))
        hi = math.log10(max(r["total_tokens"] for r in rr))
        for c in levels_in(rows, meta["run_id"]):
            xs = np.array([r["total_tokens"] for r in rr if r["condition"] == c], dtype=float)
            fig, axes = plt.subplots(len(widths), 2, figsize=(7.6, 8.6), sharex=True)
            for row, w in enumerate(widths):
                edges = 10 ** np.arange(lo - w, hi + 2 * w, w)
                for col, yscale in enumerate(("linear", "log")):
                    ax = axes[row][col]
                    ax.hist(xs, bins=edges, color="#4c78a8", edgecolor="#22333f", lw=0.4)
                    # 生の点も下端に重ねる。ビンに丸める前の位置が分かるように。
                    base = 0.35 if yscale == "log" else 0.0
                    ax.plot(xs, np.full(len(xs), base), "|", color="#cf222e",
                            ms=7, mew=1.0, clip_on=False)
                    ax.set_xscale("log")
                    ax.set_yscale(yscale)
                    if yscale == "log":
                        ax.set_ylim(0.3, max(3, len(xs)))
                    ax.tick_params(labelsize=7)
                    ax.set_title("bin=%.2f dex, freq=%s" % (w, yscale), fontsize=8)
                    if row == len(widths) - 1:
                        ax.set_xlabel("total tokens (log)", fontsize=8)
                    if col == 0:
                        ax.set_ylabel("count", fontsize=8)
            fig.suptitle("%s / %s  (n=%d)  4 bin widths x 2 frequency scales\n"
                         "red ticks = the raw points, unbinned" % (meta["run_id"], c, len(xs)),
                         fontsize=9)
            fig.tight_layout(rect=[0, 0, 1, 0.95])
            path = os.path.join(HIST_DIR, "%s__%s.png" % (meta["run_id"], c))
            fig.savefig(path, dpi=140)
            plt.close(fig)
            made.append(path)
    return made


def fig_attempts_vs_tokens(runs, rows):
    """試行回数で消費がほぼ決まっているのか、別の軸が効いているのかを見る。"""
    rr = [r for r in rows if r["total_tokens"]]
    cmap = plt.get_cmap("tab10")
    lvl_color = {}
    for r in rr:
        lvl_color.setdefault(r["condition"], cmap((r["level"] or 0) % 10))

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    rng = np.random.default_rng(0)
    jitter = rng.uniform(-0.16, 0.16, len(rr))

    panels = [
        ("total_tokens", "total tokens (log)"),
        ("prompt_tokens", "prompt tokens, summed over attempts (log)"),
        ("completion_tokens", "completion tokens, summed over attempts (log)"),
    ]
    for ax, (key, ylab) in zip(axes.flat, panels):
        for j, r in enumerate(rr):
            ax.scatter(r["attempts"] + jitter[j], max(r[key], 1), s=22,
                       color=lvl_color[r["condition"]],
                       marker="o" if r["success"] else "x",
                       lw=0 if r["success"] else 1.1, alpha=0.85)
        ax.set_yscale("log")
        ax.set_xlabel("attempts used in the trial", fontsize=8)
        ax.set_ylabel(ylab, fontsize=8)
        ax.grid(alpha=0.25, lw=0.5)
        ax.tick_params(labelsize=8)

    # 4枚目: 試行回数を割り引いた「1試行あたりの生成量」。試行回数以外の軸があるか。
    ax = axes.flat[3]
    for j, r in enumerate(rr):
        if not r["mean_completion_per_attempt"]:
            continue
        ax.scatter(r["attempts"] + jitter[j], r["mean_completion_per_attempt"], s=22,
                   color=lvl_color[r["condition"]],
                   marker="o" if r["success"] else "x",
                   lw=0 if r["success"] else 1.1, alpha=0.85)
    ax.set_xlabel("attempts used in the trial", fontsize=8)
    ax.set_ylabel("mean completion tokens per attempt", fontsize=8)
    ax.grid(alpha=0.25, lw=0.5)
    ax.tick_params(labelsize=8)

    handles = [Line2D([], [], ls="", marker="o", color=lvl_color[c], label=c)
               for c in sorted(lvl_color)]
    handles += [Line2D([], [], ls="", marker="o", color="#666666", label="correct"),
                Line2D([], [], ls="", marker="x", color="#666666", label="not correct")]
    fig.legend(handles=handles, fontsize=7, loc="lower center", ncol=6)
    fig.suptitle("Attempts vs token consumption (all v3_levels runs pooled; marker = correctness)",
                 fontsize=10)
    fig.tight_layout(rect=[0, 0.10, 1, 0.96])
    fig.savefig(os.path.join(FIG_DIR, "fig05_attempts_vs_tokens.png"), dpi=160)
    plt.close(fig)


def fig_within_trial(runs, rows):
    """1試行の中でトークンがどう積み上がるか。会話を積むので入力側が伸びる。"""
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    rr = [r for r in rows if r["attempt_totals"]]

    ax = axes[0]
    for r in rr:
        cum = np.cumsum(r["attempt_totals"])
        ax.plot(range(1, len(cum) + 1), cum, lw=0.7, alpha=0.5,
                color="#1a7f37" if r["success"] else "#cf222e")
    ax.set_yscale("log")
    ax.set_xlabel("attempt index", fontsize=8)
    ax.set_ylabel("cumulative total tokens (log)", fontsize=8)
    ax.set_title("cumulative consumption within a trial", fontsize=9)

    ax = axes[1]
    for r in rr:
        ax.plot(range(1, len(r["attempt_prompts"]) + 1), r["attempt_prompts"], lw=0.7, alpha=0.5,
                color="#1a7f37" if r["success"] else "#cf222e")
    ax.set_xlabel("attempt index", fontsize=8)
    ax.set_ylabel("prompt tokens of that attempt", fontsize=8)
    ax.set_title("input side grows because the conversation is kept", fontsize=9)

    ax = axes[2]
    for r in rr:
        ax.plot(range(1, len(r["attempt_completions"]) + 1), r["attempt_completions"], lw=0.7,
                alpha=0.5, color="#1a7f37" if r["success"] else "#cf222e")
    ax.set_xlabel("attempt index", fontsize=8)
    ax.set_ylabel("completion tokens of that attempt", fontsize=8)
    ax.set_title("generated tokens per attempt", fontsize=9)

    for ax in axes:
        ax.grid(alpha=0.25, lw=0.5)
        ax.tick_params(labelsize=8)
    axes[0].legend(handles=[Line2D([], [], color="#1a7f37", label="correct"),
                            Line2D([], [], color="#cf222e", label="not correct")], fontsize=7)
    fig.suptitle("Per-attempt breakdown inside each trial (all v3_levels runs)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(os.path.join(FIG_DIR, "fig06_within_trial.png"), dpi=160)
    plt.close(fig)


def fig_first_attempt(runs, rows):
    """試行回数以外の軸の候補: 1試行目の生成量。総トークンとの関係を見る。"""
    rr = [r for r in rows if r["first_completion"]]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    cmap = plt.get_cmap("viridis")
    norm = matplotlib.colors.Normalize(vmin=1, vmax=max(r["attempts"] for r in rr))
    sc = axes[0].scatter([r["first_completion"] for r in rr], [r["total_tokens"] for r in rr],
                         c=[r["attempts"] for r in rr], cmap=cmap, norm=norm, s=24, lw=0)
    axes[0].set_yscale("log")
    axes[0].set_xlabel("completion tokens of attempt 1", fontsize=8)
    axes[0].set_ylabel("total tokens of the trial (log)", fontsize=8)
    axes[0].set_title("first-attempt verbosity vs trial total", fontsize=9)

    axes[1].scatter([r["attempts"] for r in rr], [r["first_completion"] for r in rr],
                    c=[r["attempts"] for r in rr], cmap=cmap, norm=norm, s=24, lw=0)
    axes[1].set_xlabel("attempts used", fontsize=8)
    axes[1].set_ylabel("completion tokens of attempt 1", fontsize=8)
    axes[1].set_title("is the first answer already longer in long trials?", fontsize=9)
    for ax in axes:
        ax.grid(alpha=0.25, lw=0.5)
        ax.tick_params(labelsize=8)
    fig.colorbar(sc, ax=axes, fraction=0.03, pad=0.02, label="attempts")
    fig.suptitle("A second axis besides attempt count", fontsize=10)
    fig.savefig(os.path.join(FIG_DIR, "fig07_first_attempt.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)


def main():
    os.makedirs(HIST_DIR, exist_ok=True)
    runs, rows = load_runs()
    fig_strip_raw(runs, rows)
    fig_strip_by_attempts(runs, rows)
    fig_strip_by_success(runs, rows)
    fig_strip_by_task(runs, rows)
    hists = fig_hist_binwidths(runs, rows)
    fig_attempts_vs_tokens(runs, rows)
    fig_within_trial(runs, rows)
    fig_first_attempt(runs, rows)
    print("figures written:", 7 + len(hists))


if __name__ == "__main__":
    main()
