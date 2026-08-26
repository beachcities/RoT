# -*- coding: utf-8 -*-
"""計器v2「分布プローブ」の組を作る（v4_distribution）。

仕様の正本は `paper/notes/instrument-v2-distribution-probe.md` の **v2.0凍結版**。
ここはその実装で、**v3 とは実装非互換**（再試行ループを廃し、一発勝負で n 標本を引く）。
v3 の数値とは直接比較しない。

## 格子（仕様 第3節）

    的の記載数 t ∈ {0, 1, 2} × 外れの記載数 d ∈ {0, 1, 2, 3, 4}

不透明コードは6つ（303/404/505/606/707/808）。的は 707・505 の2つ、外れは残り4つ。
**文書に書くのは、選ばれた不透明コードの意味だけ。** 101/201/202 は社名から推せるので
定義を置かない（置くと「書いた／書かない」の意味が二重になる）。

## 変種（仕様 第3節）

変種は**的の選び方×外れの選び方の直積**で、変種数は

    V = C(2, t) · C(4, d)

    t=0行: 1, 4, 6, 4, 1
    t=1行: 2, 8, 12, 8, 2
    t=2行: 1, 4, 6, 4, 1

## 残存仮説数と偶然水準（仕様 第4節）

    H = C(6 − t − d, 2 − t)      γ = 1 / H

    t=0断面: H = 15, 10, 6, 3, 1
    t=1断面: H =  5,  4, 3, 2, 1
    t=2断面: H =  1（全 d、γ=1）

**H は「どれを」書いたかに依らず「いくつ」書いたかで決まる**ので、変種間で共通。
集計の横軸は d ではなく **x = log2 H**（外れ1個の追加は等量の情報増加ではなく、
H の縮み方は組合せで決まる）。

## 標本設計（仕様 第3節・完全交差・均衡）

**同一セル内では、同じ seed 集合を全変種に交差させる。** 変種ごとに別の seed を
振ると、変種効果と seed 効果がふたたび交絡する。

    n = V × k        k = 変種あたりの seed 数（最低2）

seed は**入れ子の master 集合**から先頭順に取る。全セルが少なくとも S1・S2 を
共有するので、d 方向・t 方向の比較が paired に近い構造を持つ。

    V=1  → k=12 → S1〜S12        V=6  → k=2  → S1〜S2
    V=2  → k=6  → S1〜S6         V=8  → k=2  → S1〜S2
    V=4  → k=3  → S1〜S3         V=12 → k=2  → S1〜S2

**master 帯はスモーク（20260820〜20260829）と重ねない。**
"""

import argparse
import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "v4_distribution"

# v3 と同じ17レコード。データは作り直さない（文書生成側で意味を書くかどうかだけ変える）。
SOURCE = HERE / "v3_levels" / "l6_codes_doc.json"

TARGETS = ["707", "505"]                       # 的（専門サービス業・学術研究業）
DECOYS = ["303", "404", "606", "808"]          # 外れ（社名から推せない残り4つ）

# 走行ごとに事前登録する master seed 集合。**スモーク帯と重ねない。**
MASTER_SEEDS = [20260901 + i for i in range(12)]      # S1 … S12

# セル別の標本数（仕様 第3節「パイロットの最小設計」）。合計200。
N_TABLE = {
    0: [12, 12, 12, 12, 12],
    1: [12, 16, 24, 16, 12],
    2: [12, 12, 12, 12, 12],
}

QUERY = ("専門サービス業と学術研究業に属する企業について、"
         "従業員数の合計は何人ですか。数値のみを答えてください。")
GROUND_TRUTH = "228"


def variant_count(t, d):
    """V = C(2,t)·C(4,d)。的の選び方 × 外れの選び方の直積。"""
    return math.comb(2, t) * math.comb(4, d)


def hypotheses(t, d):
    """残存仮説数 H = C(6−t−d, 2−t)。的が全部書いてあれば 1。"""
    u = 6 - t - d
    need = 2 - t
    if need == 0:
        return 1
    if u < need:
        return 0
    return math.comb(u, need)


def gamma(t, d):
    """偶然水準 γ = 1/H。**測った分布はこれと突き合わせる。**"""
    h = hypotheses(t, d)
    return 1.0 / h if h else 0.0


def document(defs, source):
    """選ばれたコードの意味だけを載せた文書。"""
    if not defs:
        return {"records": source["records"]}
    return {"code_definition": {c: source["code_definition"][c] for c in defs},
            "records": source["records"]}


def variants_for(t, d):
    """(t, d) の変種を、的の選び方 × 外れの選び方で並べる（決定的な順）。"""
    return [list(ts) + list(ds)
            for ts in itertools.combinations(TARGETS, t)
            for ds in itertools.combinations(DECOYS, d)]


def design_for(t, d):
    """完全交差・均衡の標本設計。**均衡が取れない n は採らない。**"""
    v = variant_count(t, d)
    n = N_TABLE[t][d]
    if n % v:
        raise SystemExit(f"t={t} d={d}: n={n} が V={v} で割り切れない（均衡が取れない）")
    k = n // v
    if k < 2:
        raise SystemExit(f"t={t} d={d}: 変種あたり {k} seed では最低2に足りない")
    if k > len(MASTER_SEEDS):
        raise SystemExit(f"t={t} d={d}: master seed が {k} 本に足りない")
    return {"n": n, "variants": v, "seeds_per_variant": k, "seeds": MASTER_SEEDS[:k]}


def main():
    ap = argparse.ArgumentParser(description="v4_distribution の組を作る")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = json.load(open(SOURCE, encoding="utf-8"))

    conditions = []
    total = 0
    for t in (0, 1, 2):
        for d in (0, 1, 2, 3, 4):
            picks = variants_for(t, d)
            assert len(picks) == variant_count(t, d), (t, d)
            design = design_for(t, d)
            name = f"t{t}_d{d}"
            (out / f"{name}.json").write_text(
                json.dumps({"variants": [document(v, source) for v in picks],
                            "variant_codes": picks},
                           ensure_ascii=False, indent=2), encoding="utf-8")
            h = hypotheses(t, d)
            conditions.append({
                "name": name, "file": f"{name}.json",
                "t": t, "d": d,
                "V": design["variants"],
                "H": h,
                "log2H": math.log2(h) if h else None,
                "gamma": gamma(t, d),
                "unknown_codes": 6 - t - d,
                "targets_unwritten": 2 - t,
                "design": design,
                # 外れ部分集合は標本間で振る。**固定すると、そのセルで観測できるのが
                # 1変種だけになり、変種効果を分離できない**——測った散らばりが
                # 課題の性質なのか、たまたま選んだ残候補集合の癖なのかを分けられない。
                # 振ったうえで variant×seed を二段で記録すれば、変種内と変種間の
                # 揺れを分解できる。
                "arm": "varied",
                # t=2 は m/w 推定の対象外で、十分情報条件の lapse を測る系列。
                "series": "lapse" if t == 2 else "threshold",
            })
            total += design["n"]

    (out / "conditions.json").write_text(
        json.dumps({"master_seeds": MASTER_SEEDS, "total_samples": total,
                    "conditions": conditions}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    tasks = [{
        "task_id": "task_06",
        "group": "code_opaque",
        "query": QUERY,
        "ground_truth": GROUND_TRUTH,
        "needs": "業種コード 707 と 505 の意味。どちらも社名からは推せず、消去法でも辿れない",
        "escape_route": {
            "escapable": False,
            "route": "社名から推せない業種が6コード、各2社ずつ。的を絞る手がかりは"
                     "文書に書かれた意味だけで、書かれていない分は残候補からの"
                     "当て推量になる（その確率が条件ごとの gamma）",
        },
    }]
    (out / "tasks.json").write_text(json.dumps(tasks, ensure_ascii=False, indent=2),
                                    encoding="utf-8")

    print(f"書き出した: {out}  条件 {len(conditions)} 件 / 標本 {total}")
    print(f"master seed: S1..S{len(MASTER_SEEDS)} = "
          f"{MASTER_SEEDS[0]}..{MASTER_SEEDS[-1]}")
    print(f"\n{'セル':9s} {'V':>3s} {'H':>3s} {'log2H':>7s} {'γ':>8s} "
          f"{'n':>4s} {'k':>3s}  seed")
    for c in conditions:
        dz = c["design"]
        lg = c["log2H"]
        print(f"t={c['t']} d={c['d']}   {c['V']:>3d} {c['H']:>3d} "
              f"{(lg if lg is not None else float('nan')):>7.3f} "
              f"{c['gamma']:>8.4f} {dz['n']:>4d} {dz['seeds_per_variant']:>3d}  "
              f"S1..S{dz['seeds_per_variant']}")


if __name__ == "__main__":
    main()
