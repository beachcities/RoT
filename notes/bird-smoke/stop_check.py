# -*- coding: utf-8 -*-
"""BIRD Contamination smoke — 手順1〜3（モデル前 STOP 条件の機械確認）。

**モデルは呼ばない。** snapshot（`snapshot.json` に sha256 を記録）だけを使う。

    python stop_check.py <body.csv> <codelist.html> <tokenizer.json>

出すもの：課題対象コード集合、T1・T2 の正答、隣接誤解釈、S3/S5/弁別/S6/S2 の判定。
"""

import collections
import csv
import io
import json
import pathlib
import re
import sys

X_TOK = 47104          # chat 側で凍結済みの上限
MIN_DIFF = 5           # 弁別条件：正答と誤解釈の差


def load_codelist(path):
    """dbview の HTML から (コード, 名称) を機械可読化する。

    同じコードに旧称が併記されている行があるので、**最初に現れた名称を採る**。
    """
    t = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    out = {}
    for c, n in re.findall(r'\b(\d{5})_([^"<,\n]{2,60})', t):
        n = n.strip()
        if n and c not in out:
            out[c] = n
    return out


def load_body(path):
    s = pathlib.Path(path).read_bytes().decode("cp932", errors="replace")
    rows = [l.split(",") for l in s.splitlines()]
    return s, [r for r in rows if len(r) > 5 and re.match(r"^\d{5}", r[2])]


def leaf_codes(codes):
    """最下層のコード。上位層は下位層の集約なので課題から外す。"""
    L1 = {c for c in codes if c.endswith("000")}
    L2 = {c for c in codes if c.endswith("00") and c not in L1}
    L3 = {c for c in codes if not c.endswith("00")}
    leaf = set(L3)
    leaf |= {c for c in L2 if not any(x[:3] == c[:3] for x in L3)}
    leaf |= {c for c in L1 if not any(x[:2] == c[:2] and x != c for x in L2)}
    return leaf, L1, L2, L3


def num(v):
    v = v.strip()
    return int(v) if v != "-" and v.lstrip("-").isdigit() else 0


def main(body_p, code_p, tok_p):
    codelist = load_codelist(code_p)
    raw, data = load_body(body_p)
    codes = sorted({r[2][:5] for r in data})
    leaf, L1, L2, L3 = leaf_codes(codes)

    def val(area, code, sex):
        for r in data:
            if r[1] == area and r[2][:5] == code and r[3] == sex:
                return r[4].strip()
        return None

    # 非縮退＝全国・性総数が '-' でも 0 でもない最下層コード
    nondeg = [c for c in sorted(leaf)
              if (v := val("全国", c, "総数")) is not None and v != "-"
              and v.replace(",", "").isdigit() and int(v.replace(",", "")) != 0]
    TGT, NXT = nondeg[:4], nondeg[4]

    # --- 課題用スコープ（S6 の除外規則）---
    # 派生を機械規則で一意に落とす：地域は都道府県のみ（全国・指定都市再掲・不詳を除く）、
    # 性は男女のみ（総数は男+女の派生）、コードは最下層のみ（上位層は集約）。
    PREF = sorted({r[1] for r in data if r[1].endswith(("都", "道", "府", "県"))})
    scope = [r for r in data if r[1] in PREF and r[3] in ("男", "女") and r[2][:5] in leaf]

    def total(cs, sexes):
        return sum(num(r[4]) for r in scope if r[2][:5] in cs and r[3] in sexes)

    T1 = total({TGT[0], TGT[1]}, {"男", "女"})
    T2 = total({TGT[2], TGT[3]}, {"男"})

    mis1 = {f"(a) {TGT[0]}のみ": total({TGT[0]}, {"男", "女"}),
            f"(a) {TGT[1]}のみ": total({TGT[1]}, {"男", "女"}),
            f"(b) +{NXT}": total({TGT[0], TGT[1], NXT}, {"男", "女"})}
    mis2 = {f"(a) {TGT[2]}のみ": total({TGT[2]}, {"男"}),
            f"(a) {TGT[3]}のみ": total({TGT[3]}, {"男"}),
            f"(b) +{NXT}": total({TGT[2], TGT[3], NXT}, {"男"}),
            "(c) 性=総数": total({TGT[2], TGT[3]}, {"男", "女"})}

    discrim = all(abs(T1 - v) >= MIN_DIFF for v in mis1.values()) and \
              all(abs(T2 - v) >= MIN_DIFF for v in mis2.values())

    # --- S3: 死因×性の2軸交差が独立観測セルとして立つか ---
    S3 = any(r[2][:5] in {TGT[2], TGT[3]} and r[3] == "男" for r in scope)

    # --- S5: 正答が0でも全件でもない ---
    S5 = T1 > 0 and T2 > 0 and T1 < total(leaf, {"男", "女"}) and T2 < total(leaf, {"男"})

    # --- S6: 独立二経路（手分割 / csv モジュール）---
    B1 = B2 = nB = 0
    for f in csv.reader(io.StringIO(raw)):
        if len(f) <= 5 or not re.match(r"^\d{5}", f[2]):
            continue
        area, code, sex, v = f[1], f[2][:5], f[3], f[4].strip()
        if area not in PREF or sex not in ("男", "女") or code not in leaf:
            continue
        nB += 1
        n = int(v) if v != "-" and v.lstrip("-").isdigit() else 0
        if code in (TGT[0], TGT[1]):
            B1 += n
        if code in (TGT[2], TGT[3]) and sex == "男":
            B2 += n
    S6 = (nB == len(scope) and B1 == T1 and B2 == T2)

    # --- S2: 課題用スコープの直列化トークン（3形）---
    from tokenizers import Tokenizer
    TOK = Tokenizer.from_file(tok_p)
    full = [{"地域": r[1], "分類": r[2], "性": r[3], "死亡数": r[4].strip()} for r in scope]
    mini = [[r[1], r[2][:5], r[3], r[4].strip()] for r in scope]
    toks = {
        "A 整形・名称つき": len(TOK.encode(json.dumps(full, ensure_ascii=False, indent=2)).ids),
        "B 圧縮・名称つき": len(TOK.encode(json.dumps(full, ensure_ascii=False, separators=(",", ":"))).ids),
        "C 圧縮・列削減(配列)": len(TOK.encode(json.dumps(mini, ensure_ascii=False, separators=(",", ":"))).ids),
    }
    S2 = min(toks.values()) <= X_TOK

    out = dict(codelist_codes=len(codelist), body_codes=len(codes),
               leaf=len(leaf), nondeg=len(nondeg), target=TGT, next=NXT,
               pref=len(PREF), scope_cells=len(scope),
               T1=T1, T2=T2, mis1=mis1, mis2=mis2,
               S3=S3, S5=S5, discrim=discrim, S6=S6, S2=S2, tokens=toks)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print("\n=== STOP 条件 ===")
    for k in ("S3", "S5", "discrim", "S6", "S2"):
        print(f"  {k}: {'通過' if out[k] else '**該当（停止）**'}")
    return 0 if all(out[k] for k in ("S3", "S5", "discrim", "S6", "S2")) else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
