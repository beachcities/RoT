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


# 棄権（abstention）の判定規則。仕様 第7節。
#
# **数値0の機械的判定ではない。** 0 が正当な数値解になり得る課題への拡張に備え、
# 「対応が無い」と「だから出せない」を**両方**述べていることを要件とする。
# 強い言い切り（下の STRONG）は単独で棄権とみなす。
#
# 判定にかけるのは最終回答の本文のみ（思考テキストは見ない）。
ABSTAIN_STRONG = [
    "特定できません", "特定することができません", "特定できない",
    "回答できません", "答えられません",
    "該当する企業は存在しません", "該当する企業はありません", "該当なし",
]
ABSTAIN_ABSENT = [           # 対応・定義が無いこと
    "定義されていない", "定義がありません", "定義はありません", "定義が含まれ",
    "含まれていません", "提供されていません", "提供されていない",
    "記載されていません", "記載がありません", "マッピング", "対応関係",
    "不明", "判別できません",
]
ABSTAIN_UNABLE = [           # だから出せないこと
    "できません", "できない", "判断できません", "0 となります", "0となります",
    "0 です", "0です", "存在しません", "ありません",
]


def abstention(text):
    """棄権かどうかと、当たった語を返す。**当たった語も記録する**（監査のため）。"""
    t = text or ""
    strong = [w for w in ABSTAIN_STRONG if w in t]
    if strong:
        return True, strong
    absent = [w for w in ABSTAIN_ABSENT if w in t]
    unable = [w for w in ABSTAIN_UNABLE if w in t]
    if absent and unable:
        return True, absent[:2] + unable[:2]
    return False, []


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
    """1セルぶんの読み取り量。**二部モデル**（仕様 第7節）。

    棄権率は独立の指標として出し、山の統計は**非棄権の数値回答**で計算する
    （分母は「非棄権かつ数値が取れた」件数）。棄権込みの値は感度分析として併記し、
    そちらの分母も実際に数値が取れた件数に揃える。
    **棄権率の分母と総トークンは全標本のまま。**
    """
    for r in rows:
        flag, hits = abstention(r.get("final_answer"))
        r["棄権"] = flag
        r["棄権の根拠"] = hits
    abstained = [r for r in rows if r["棄権"]]
    kept = [r for r in rows if not r["棄権"]]
    answered = [r for r in kept if r.get("final_number") is not None]
    values = [r["final_number"] for r in answered]
    groups = cluster(values)
    sizes = [len(g) for g in groups]
    n = len(rows)
    # **山の統計の分母は「非棄権かつ数値が取れた」件数。** values はもともと
    # 数値回答だけなので、分母を非棄権全件にすると、数値を取り出せなかった標本の
    # ぶんだけ占有率が下振れする。取り出せなかった件数は黙って消さず、
    # 独立の項目として出す。
    m = len(answered)
    unparsed = len(kept) - len(answered)
    correct_group = None
    for g in groups:
        if any(abs(v - truth) < 1e-9 for v in g):
            correct_group = g
            break
    counts = list(Counter(values).values())
    # 感度分析: 棄権を混ぜたまま同じ計算をするとどうなるか
    all_values = [r["final_number"] for r in rows if r.get("final_number") is not None]
    all_groups = cluster(all_values)
    all_correct = next((g for g in all_groups
                        if any(abs(v - truth) < 1e-9 for v in g)), None)
    # 感度側も同じ原則。分母は実際に数値が取れた件数。
    ma = len(all_values)
    # 「対応がデータに無いので該当0」と述べて 0 を答える型。誤答とは性質が違うので
    # 数え分ける。**山推定には手を入れない**（0 も1つの値として山に入る）。
    zeros = sum(1 for v in values if v == 0)
    return {
        "棄権数": len(abstained),
        "棄権率": (len(abstained) / n) if n else 0.0,
        "非棄権数": len(kept),
        "非棄権だが数値抽出不能": unparsed,
        "感度_棄権込み": {
            "山の数": len(all_groups),
            "数値が取れた": ma,
            "最大山の占有率": (max((len(g) for g in all_groups), default=0) / ma) if ma else 0.0,
            "正解山の占有率": (len(all_correct) / ma) if all_correct and ma else 0.0,
            "回答エントロピー": entropy(list(Counter(all_values).values())),
        },
        "0回答数": zeros,
        "標本数": n,
        "数値が取れた": len(answered),
        "山の数": len(groups),
        "最大山の占有率": (max(sizes) / m) if sizes and m else 0.0,
        "正解山の占有率": (len(correct_group) / m) if correct_group and m else 0.0,
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
    header = (f"{'条件':10s} {'V':>3s} {'log2H':>6s} {'n':>4s} {'棄権率':>7s} "
              f"{'不能':>4s} {'分母':>4s} {'山':>3s} {'最大山':>7s} {'正解山':>7s} "
              f"{'γ':>7s} {'エントロピー':>12s} {'総token':>9s}")
    print(header)
    print("-" * len(header))
    out = {}
    for name in sorted(by):
        g = spec.get(name, {}).get("gamma")
        d = describe(by[name], truth, g)
        out[name] = d
        meta = spec.get(name, {})
        lg = meta.get("log2H")
        print(f"{name:10s} {meta.get('V', 0):>3d} "
              f"{(lg if lg is not None else float('nan')):>6.2f} "
              f"{d['標本数']:>4d} {d['棄権率']:>7.2f} "
              f"{d['非棄権だが数値抽出不能']:>4d} {d['数値が取れた']:>4d} {d['山の数']:>3d} "
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
    print("棄権（仕様 第7節）に当たった標本:")
    any_hit = False
    for name in sorted(by):
        for r in by[name]:
            if r.get("棄権"):
                any_hit = True
                print(f"    {name} 反復{r['repeat']} 変種{r.get('variant')} "
                      f"seed{r.get('seed')} 根拠={r.get('棄権の根拠')}")
    if not any_hit:
        print("    なし")
    print()
    print("山の統計の分母は**非棄権かつ数値が取れた件数**。棄権込みは感度分析として各セルの")
    print("「感度_棄権込み」に入れてある。総トークンは全標本。")
    print("**n が小さいので検定はしない。** 正解山の占有率と γ を並べて置くだけにする。")
    print("山の数は隙間で切った素朴な推定で、想定山数は使っていない。")
    return out


if __name__ == "__main__":
    sys.exit(0 if main() else 0)
