# -*- coding: utf-8 -*-
"""計器v2「分布プローブ」の集計。

    python summarize_v4.py results/run_XXXX.json

仕様の正本は `paper/notes/instrument-v2-distribution-probe.md`。

**壊れるとは一試行の結末ではなく、同条件で引いた出力分布が正解に集中しなくなること。**
だから読むのは正答率ではなく分布の形で、五つの量を出す。

    山の数 / 最大山の占有率 / 正解山の占有率 / 散らばり（回答エントロピー） / 総トークン

山の数は指定しない。**数直線上の隙間で切る素朴な実装**から始める（仕様の指示）。
想定山数は答え合わせ側にのみ置き、推定には使わない。

各セルには計算可能な偶然水準 γ が付く（条件の定義に入っている）。正解山の占有率を
γ と並べて置く。**n=10 はパイロット水準なので、検定はしない。並べるだけにする。**
"""

import argparse
import json
import math
import sys
from collections import Counter


def cluster(values, rel_gap=0.05):
    """数直線に並べ、隣との隔たりが広いところで切る。

    切る基準は「値の広がりに対する相対的な隙間」。絶対値で切ると、桁の違う答えが
    出たときに全部が1つの山になる。**素朴な実装であることを承知で使う** ——
    山の数を先に決めない、という点だけが要件。
    """
    if not values:
        return []
    xs = sorted(values)
    if len(xs) == 1:
        return [xs]
    span = xs[-1] - xs[0]
    if span == 0:
        return [xs]
    threshold = span * rel_gap
    groups = [[xs[0]]]
    for a, b in zip(xs, xs[1:]):
        if b - a > threshold:
            groups.append([b])
        else:
            groups[-1].append(b)
    return groups


def entropy(counts):
    """回答の散らばり。**同じ値に固まれば0、ばらけるほど大きい。**"""
    total = sum(counts)
    if total <= 0:
        return 0.0
    out = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            out -= p * math.log(p, 2)
    return out


def describe(rows, truth, gamma):
    """1セルぶんの読み取り量。"""
    answered = [r for r in rows if r.get("final_number") is not None]
    values = [r["final_number"] for r in answered]
    groups = cluster(values)
    sizes = [len(g) for g in groups]
    n = len(rows)
    correct_group = None
    for g in groups:
        if any(abs(v - truth) < 1e-9 for v in g):
            correct_group = g
            break
    counts = list(Counter(values).values())
    return {
        "標本数": n,
        "数値が取れた": len(answered),
        "山の数": len(groups),
        "最大山の占有率": (max(sizes) / n) if sizes and n else 0.0,
        "正解山の占有率": (len(correct_group) / n) if correct_group and n else 0.0,
        "回答エントロピー": entropy(counts),
        "gamma": gamma,
        "総トークン": sum(r.get("total_tokens") or 0 for r in rows),
        "山": [{"代表値": g[0], "件数": len(g),
                "正解か": bool(correct_group is not None and g is correct_group)}
               for g in groups],
    }


def final_number(row):
    """最終回答から数値を取り出す。run_benchmark の採点と同じ規則で最後の数値を採る。"""
    text = row.get("final_answer") or ""
    import re
    import unicodedata
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=\d),(?=\d)", "", normalized)
    lines = [ln for ln in normalized.splitlines() if ln.strip()]
    for line in reversed(lines or [normalized]):
        found = re.findall(r"\d+", line)
        if found:
            return int(found[-1])
    return None


def main():
    ap = argparse.ArgumentParser(description="分布プローブの集計")
    ap.add_argument("path")
    ap.add_argument("--rel-gap", type=float, default=0.05,
                    help="山を切る隙間の閾値（値の広がりに対する比）")
    args = ap.parse_args()

    run = json.load(open(args.path, encoding="utf-8"))
    spec = {c["name"]: c for c in run.get("condition_spec", [])}
    truth = None
    for t in run.get("inputs", {}).get("tasks", []):
        truth = int(t["ground_truth"])
    by = {}
    for r in run["results"]:
        r = dict(r, final_number=final_number(r) if r.get("status") == "ok" else None)
        by.setdefault(r["condition"], []).append(r)

    print(f"組 {run['suite']} / モデル {run['models']} / thinking {run.get('thinking_mode')}")
    print(f"試行上限 {run['max_attempts']}（1 なら一発勝負）/ 反復 {run['repeats']}")
    print(f"inputs 指紋 {run['fingerprint']['inputs']}")
    print(f"seed 群 {sorted({r.get('seed') for r in run['results']})}")
    print()
    header = (f"{'条件':18s} {'n':>3s} {'山':>3s} {'最大山':>7s} {'正解山':>7s} "
              f"{'γ':>7s} {'エントロピー':>12s} {'総token':>9s}")
    print(header)
    print("-" * len(header))
    out = {}
    for name in sorted(by):
        g = spec.get(name, {}).get("gamma")
        d = describe(by[name], truth, g)
        out[name] = d
        print(f"{name:18s} {d['標本数']:>3d} {d['山の数']:>3d} "
              f"{d['最大山の占有率']:>7.2f} {d['正解山の占有率']:>7.2f} "
              f"{(g if g is not None else float('nan')):>7.3f} "
              f"{d['回答エントロピー']:>12.3f} {d['総トークン']:>9,}")
    print()
    for name in sorted(by):
        print(f"{name} の山:")
        for m in out[name]["山"]:
            mark = "  ← 正解" if m["正解か"] else ""
            print(f"    {m['代表値']:>12} × {m['件数']}{mark}")
    print()
    print("**n が小さいので検定はしない。** 正解山の占有率と γ を並べて置くだけにする。")
    print("山の数は隙間で切った素朴な推定で、想定山数は使っていない。")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
