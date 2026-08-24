# -*- coding: utf-8 -*-
"""稿第1節の「少なからぬ部分」を数える。

失敗した試行の思考を文単位に割り、各文を3つに分ける。

  A: データ側の欠落への言及・当て推量（コード/単位/ラベル/対応表/スキーマが無い、
     あるいはそれを推し量っている）
  B: 問いの側の曖昧さへの言及（何を答えればよいか、誰を含めるか）
  C: その他（計算、データの読み上げ、答えの整形、自分の過去の答えの点検）

分類にLLMは使わない。語彙による規則だけで、`derive_requirements.py` の
「引き金＋対象」という組み方をそのまま広げたもの。

**主語ではなく対象で分ける。** `derive_requirements.py` は「the question doesn't
specify」のように問いを主語にした文を落とすが、ここでは欠落している当のものが
データ側の記述か（コードの意味、単位、ラベル）、問いの側か（何を出力するか、
誰を含めるか）で分ける。同じ文が両方に触れる場合は B に寄せる（A を過大にしない）。
その分の件数は overlap として別に出す。

    python quantify_section1.py                    # 既定の2ラン
    python quantify_section1.py --show A 3         # 該当文を見る
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
BASE = Path(__file__).resolve().parent.parent

RUNS = [
    ("Olmo (オープンモデル)", "results/run_20260823T124213Z.json"),
    ("Qwen (オープンウェイト)", "results/run_20260824T061642Z.json"),
]

# --- 引き金 ---------------------------------------------------------------
# 「無い」と述べている。derive_requirements.py の MISSING を広げたもの。
GAP = re.compile(
    r"(?:does\s?n[o']t|do\s?n[o']t|did\s?n[o']t|is\s?n[o']t|are\s?n[o']t|was\s?n[o']t|"
    r"cannot|can\s?not|can[''`]t|unable to|without)\s+"
    r"(?:\w+\s+){0,3}?"
    r"(?:list|have|has|specify|provide|provided|include|included|define|defined|"
    r"contain|contains|given|give|gives|available|access|accessing|know|knowing|"
    r"tell|determine|map|mapping|definitively)"
    r"|no (?:explicit|clear|direct|actual)?\s?(?:mapping|label|labels|definition|"
    r"definitions|key|description|reference|information|indication)"
    r"|lack(?:s|ing)?(?: of)?"
    r"|(?:is|are|was|were) (?:missing|absent|unavailable|not provided|not given)"
    r"|there(?:'s| is| are) no\b",
    re.I,
)

# 推し量っている。断定していない言い方。
GUESS = re.compile(
    r"\b(?:might|maybe|perhaps|probably|possibly|presumably|likely|could be|"
    r"assum(?:e|ing|ption)|guess|infer(?:red|ring)?|suppose|typically|usually|"
    r"generally|seems? to|it seems|I think|let[''`]?s (?:say|assume)|"
    r"assuming|if (?:we|I) assume|standard|conventional)\b",
    re.I,
)

# 迷いの表明。上二つに掛からない揺れを拾う。
WAVER = re.compile(r"\b(?:unclear|ambiguous|not sure|uncertain|confus(?:ed|ing)|"
                   r"hmm+|wait,|but wait|hold on)\b", re.I)

# --- 対象 -----------------------------------------------------------------
# データ側の記述。何が書かれていれば要らなかったか、にあたるもの。
DATA_OBJ = re.compile(
    r"\bindustry[_ ]?code|\bcode[_ ]?list|code_definition|unit_definition|"
    r"\bschema\b|\bmapping\b|\bJSIC\b|classification|"
    r"industry (?:name|type|names|category|categories|label)|"
    r"\bunit(?:s)?\b|million|\blabel(?:s|ed)?\b|\bdefinition(?:s)?\b|"
    r"\bfield(?:s)?\b|\bcolumn(?:s)?\b|what (?:each|the) (?:code|field|column|value)|"
    r"stands? for|\bmeans?\b|\bmeaning\b|reference (?:url|link|file)|"
    r"external (?:reference|source|data)|\bdocument(?:ation|ed)?\b|"
    r"\b(?:101|201|202|303|404|505|606|707|808)\b|"
    r"意味|定義|対応表|単位",
    re.I,
)

# 問いの側。何を答えるか、誰を含めるか、出題者が何を期待しているか。
ASK_OBJ = re.compile(
    r"\bthe (?:question|prompt|task|problem statement)\b|\bthe user\b|"
    r"they (?:want|expect|are asking|asked)|(?:answer|result) they expect|"
    r"expected answer|what (?:they|the user) (?:want|mean)|"
    r"whether to (?:include|count|exclude)|include (?:closed|inactive|only active)|"
    r"\bmade a mistake\b|\bintend(?:ed|s)?\b|求めている|意図",
    re.I,
)

SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")


def segments(text):
    """文に割る。改行も切れ目として扱う（箇条書きが多いため）。"""
    out = []
    for piece in SENT_SPLIT.split(text):
        s = piece.strip()
        if s:
            out.append(s)
    return out


def classify(s):
    """1文を A / B / C に分ける。戻り値は (種別, overlapか)。"""
    trig = bool(GAP.search(s) or GUESS.search(s) or WAVER.search(s))
    if not trig:
        return "C", False
    data = bool(DATA_OBJ.search(s))
    ask = bool(ASK_OBJ.search(s))
    if data and ask:
        return "B", True          # 両方に触れる文は B に寄せる（A を過大にしない）
    if data:
        return "A", False
    if ask:
        return "B", False
    return "C", False


def failed_attempts(path):
    d = json.load(open(BASE / path, encoding="utf-8"))
    rows = []
    for r in d["results"]:
        for a in (r.get("attempt_log") or []):
            th = (a.get("thinking") or "").strip()
            if a.get("success") is False and th:
                rows.append({
                    "cond": r["condition"], "task": r["task_id"],
                    "repeat": r.get("repeat"), "attempt": a["attempt"], "thinking": th,
                })
    return d, rows


def tally(rows):
    """水準ごとに、A/B/C の文字数と件数を集める。"""
    by_cond = defaultdict(lambda: {"A": 0, "B": 0, "C": 0, "n": 0, "overlap": 0,
                                   "segs": 0, "attempts": 0})
    hits = defaultdict(list)
    for r in rows:
        c = by_cond[r["cond"]]
        c["attempts"] += 1
        for s in segments(r["thinking"]):
            kind, ov = classify(s)
            c[kind] += len(s)
            c["segs"] += 1
            c["n"] += len(s)
            if ov:
                c["overlap"] += len(s)
            if kind in ("A", "B"):
                hits[kind].append((r, s))
    return by_cond, hits


LEVELS = ["l0_opaque", "l1_names", "l2_units_ref", "l3_units_doc", "l4_units_record",
          "l5_codes_ref", "l6_codes_doc", "l7_codes_record", "l8_flags_record", "l9_prose"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", nargs=2, metavar=("KIND", "N"), default=None)
    args = ap.parse_args()

    all_hits = {}
    for label, path in RUNS:
        d, rows = failed_attempts(path)
        by_cond, hits = tally(rows)
        all_hits[label] = hits
        tot = {"A": 0, "B": 0, "C": 0, "n": 0, "overlap": 0, "attempts": 0, "segs": 0}
        print("\n## %s — %s" % (label, d["models"][0]))
        print("   %s  失敗試行 %d 件  思考 %s 字"
              % (Path(path).name, len(rows), f"{sum(len(r['thinking']) for r in rows):,}"))
        print("\n| 水準 | 失敗試行 | 思考字数 | A | B | C | A割合 |")
        print("|---|---|---|---|---|---|---|")
        for lv in LEVELS:
            c = by_cond.get(lv)
            if not c or not c["n"]:
                print("| %s | 0 | — | — | — | — | — |" % lv)
                continue
            for k in tot:
                tot[k] += c[k]
            print("| %s | %d | %s | %s | %s | %s | **%.1f%%** |"
                  % (lv, c["attempts"], f"{c['n']:,}", f"{c['A']:,}", f"{c['B']:,}",
                     f"{c['C']:,}", 100 * c["A"] / c["n"]))
        print("| **合計** | %d | %s | %s | %s | %s | **%.1f%%** |"
              % (tot["attempts"], f"{tot['n']:,}", f"{tot['A']:,}", f"{tot['B']:,}",
                 f"{tot['C']:,}", 100 * tot["A"] / tot["n"]))
        print("\n   文の数 %s / A+B 両方に触れて B に寄せた分 %s 字 (%.1f%%)"
              % (f"{tot['segs']:,}", f"{tot['overlap']:,}",
                 100 * tot["overlap"] / tot["n"]))
        print("   overlap を A 側に寄せた場合の A割合: %.1f%%"
              % (100 * (tot["A"] + tot["overlap"]) / tot["n"]))

    if args.show:
        kind, n = args.show[0], int(args.show[1])
        for label in all_hits:
            print("\n### %s の %s 例" % (label, kind))
            for r, s in all_hits[label][kind][:n]:
                print("- [%s/%s/rep%s/att%d] %s" % (r["cond"], r["task"], r["repeat"],
                                                    r["attempt"], s[:200]))


if __name__ == "__main__":
    main()
