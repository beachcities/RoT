# -*- coding: utf-8 -*-
"""計器v2「分布プローブ」の組を作る（v4_distribution）。

仕様の正本は `paper/notes/instrument-v2-distribution-probe.md`。ここはその実装で、
**v3 とは実装非互換**（再試行ループを廃し、一発勝負で n 標本を引く）。v3 の数値とは
直接比較しない。

## 格子

軸は二本。単一の軸に潰すと、的を書く（直接情報）と外れを書く（消去法が復活する
間接情報）が交絡する。

    的の記載数 t ∈ {0, 1, 2} × 外れの記載数 d ∈ {0, 1, 2, 3, 4}

不透明コードは6つ（303/404/505/606/707/808）で、これはデータが既に持つ数であって
選定パラメータではない。的は 707・505 の2つ、外れは残り4つ。

**文書に書くのは、選ばれた不透明コードの意味だけ。** 101/201/202 は社名から
推せるので定義を置かない（置くと「書いた／書かない」の意味が二重になる）。

## ヌルモデル

残る不明コードは u = 6 − t − d。その中に未記載の的が 2 − t 個ある。無情報の
当て推量が残候補から一様に選ぶときの正答率は

    t=2 なら γ=1（的が全部書いてある）
    それ以外は γ = 1 / C(u, 2−t)、ただし u < 2−t なら的に届かないので γ=0

例: t=0,d=0 → C(6,2)=15 で 1/15。t=0,d=2 → C(4,2)=6 で 1/6。
    t=0,d=4 → C(2,2)=1 で 1。t=1,d=3 → C(2,1)=2 で 1/2。

## 部分集合の振り方

外れ4つのうちどの d 個を書くかは一通りではない。固定すると特定の残候補集合の癖を
測ることになるので、**標本間で振る側を既定とする**。実装としては、セルに変種
（variants）を並べ、ランナーが反復番号で順に選ぶ。固定側は変種を1つだけ持つ。
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
TRANSPARENT = ["101", "201", "202"]            # 社名から推せる。定義は置かない

QUERY = ("専門サービス業と学術研究業に属する企業について、"
         "従業員数の合計は何人ですか。数値のみを答えてください。")
GROUND_TRUTH = "228"


def gamma(t, d):
    """そのセルの偶然水準。**測った分布はこれと突き合わせる。**"""
    if t == 2:
        return 1.0
    u = 6 - t - d
    need = 2 - t
    if u < need:
        return 0.0
    return 1.0 / math.comb(u, need)


def document(defs, source):
    """選ばれたコードの意味だけを載せた文書を作る。"""
    data = {"records": source["records"]}
    if defs:
        data = {"code_definition": {c: source["code_definition"][c] for c in defs},
                "records": source["records"]}
    return data


def variants_for(t, d):
    """(t, d) セルの変種を、的の選び方 × 外れの選び方で並べる。

    並びは決定的（itertools の順）。**ランナーは反復番号で選ぶので、
    どの標本がどの部分集合を見たかは seed と反復番号から再現できる。**
    """
    out = []
    for tsel in itertools.combinations(TARGETS, t):
        for dsel in itertools.combinations(DECOYS, d):
            out.append(list(tsel) + list(dsel))
    return out


def main():
    ap = argparse.ArgumentParser(description="v4_distribution の組を作る")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    source = json.load(open(SOURCE, encoding="utf-8"))

    conditions = []
    for t in (0, 1, 2):
        for d in (0, 1, 2, 3, 4):
            picks = variants_for(t, d)
            for arm, chosen in (("varied", picks), ("fixed", picks[:1])):
                name = f"t{t}_d{d}_{arm}"
                payload = {
                    "variants": [document(v, source) for v in chosen],
                    "variant_codes": chosen,
                }
                (out / f"{name}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                conditions.append({
                    "name": name, "file": f"{name}.json",
                    "t": t, "d": d, "arm": arm,
                    "gamma": gamma(t, d),
                    "unknown_codes": 6 - t - d,
                    "targets_unwritten": 2 - t,
                    "variant_count": len(chosen),
                })

    (out / "conditions.json").write_text(
        json.dumps({"conditions": conditions}, ensure_ascii=False, indent=2),
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

    print(f"書き出した: {out}  条件 {len(conditions)} 件")
    for c in conditions:
        if c["arm"] == "varied":
            print(f"  t={c['t']} d={c['d']} u={c['unknown_codes']} "
                  f"gamma={c['gamma']:.4f} 変種={c['variant_count']}")


if __name__ == "__main__":
    main()
