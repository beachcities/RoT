# -*- coding: utf-8 -*-
"""思考テキストから「データ側に何が書かれているべきだったか」を逆算する。

    python derive_requirements.py results/reference/run_....json
    python derive_requirements.py <file> --show 3      # 抽出した文も出す

試論の第6節（運用のログから要求仕様を逆算する）が、実際に回るかを確かめるための実装。
手順は4段階で、それぞれこのファイルの関数に対応する。

  1. 抽出 (`extract`)  — 失敗した試行の思考から「欠けている」と述べた文を拾う
  2. 束ね (`bucket`)   — どのフィールドが無いと言っているかで束ねる
  3. 書き出し (`requirements`) — 束を要求仕様の文言として書き出す
  4. 確認 (`verify`)   — 書き足した水準で言及が消えるかを、同じ抽出器で数える

**4 が検証になっている。** 要求仕様を満たす記述が入った水準で言及が消えるなら、
逆算された仕様がその欠落を指していたことになる。抽出器を変えずに前後を数えるのが要点で、
別の基準で数え直すと検証にならない。

## 留保

* 後半の試行では、データではなく**出題者の意図を推し量る**方向に転じることがある
  （実測: Olmo-3-7B-Think が「the answer they expect」と書いている）。
  そこで生成される文は要求仕様にならない。`--first-half` で前半だけに絞れる。
* 束ねは語彙による分類であって、意味を読んでいるわけではない。
  欠落が単一の対応表という形をしていたから一意に落ちた、という可能性がある。
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- 1. 抽出 -------------------------------------------------------------
# 「無い」と述べている文を拾う。文単位で切るために前後をピリオドで区切る。
MISSING = re.compile(
    r"[^.]*?(?:"
    r"doesn't (?:list|have|specify|provide|include)"
    r"|does not (?:list|specify|provide|include)"
    r"|isn't (?:provided|specified|given|available)"
    r"|is not (?:provided|specified|given|available)"
    r"|not (?:provided|specified|given|defined) (?:here|in the data)"
    r"|no (?:explicit|clear) (?:mapping|label|definition)"
    r"|lack(?:s|ing)? (?:of )?(?:a )?(?:clear |explicit )?(?:mapping|definition)"
    r"|can't (?:see|access)|cannot (?:see|access)"
    r")[^.]*\.",
    re.I,
)

# --- 2. 束ね -------------------------------------------------------------
# 語彙で分類する。意味を読んでいるわけではない（→ 冒頭の留保）。
BUCKETS = [
    ("industry_code_meaning",
     re.compile(r"industry (?:type|code|classification)|code (?:to|-)? ?industry|"
                r"what each (?:industry )?code|code_list|jsic|業種", re.I),
     "業種コードの意味（コード → 業種名の対応表）を、データ本体に書く"),
    ("unit",
     re.compile(r"\bunit\b|million|currency|単位|百万", re.I),
     "数値の単位を、データ本体に書く"),
    ("activity_status",
     re.compile(r"active|closure|closed|status|活動|廃業", re.I),
     "活動状態の意味（列挙値が何を表すか）を、データ本体に書く"),
    ("external_reference",
     re.compile(r"url|reference|external|schema", re.I),
     "外部参照の先にある定義を、データ本体に取り込む"),
]


def extract(thinking):
    """思考テキストから「欠けている」と述べた文を返す。"""
    out = []
    for m in MISSING.finditer(thinking or ""):
        sentence = " ".join(m.group(0).split())
        if 40 <= len(sentence) <= 400:
            out.append(sentence)
    return out


def bucket(sentence):
    """1文を束に割り当てる。当てはまらなければ None。"""
    for name, pattern, _ in BUCKETS:
        if pattern.search(sentence):
            return name
    return None


def requirement_text(name):
    for key, _, text in BUCKETS:
        if key == name:
            return text
    return "（分類できなかった）"


def collect(run, failed_only=True, first_half=False):
    """試行ごとに (水準, タスク, 試行番号, 文) を集める。"""
    rows = []
    for r in run["results"]:
        if failed_only and r["success"]:
            continue
        log = r["attempt_log"]
        if first_half:
            log = log[: max(1, len(log) // 2)]
        for a in log:
            for s in extract(a.get("thinking")):
                rows.append((r["condition"], r["task_id"], a["attempt"], s))
    return rows


def verify(run):
    """4. 確認。水準ごとに、言及の件数と思考の総量を数える。

    抽出器は 1 と同じものを使う。ここを変えると検証にならない。
    """
    table = []
    for condition in run["conditions"]:
        trials = [x for x in run["results"] if x["condition"] == condition]
        chars = sum(x.get("thinking_chars") or 0 for x in trials)
        mentions = sum(
            len(extract(a.get("thinking"))) for x in trials for a in x["attempt_log"]
        )
        solved = sum(1 for x in trials if x["success"])
        table.append({
            "condition": condition,
            "solved": solved,
            "trials": len(trials),
            "thinking_chars": chars,
            "mentions": mentions,
        })
    return table


def main():
    parser = argparse.ArgumentParser(description="思考テキストから要求仕様を逆算する")
    parser.add_argument("path", nargs="?", help="結果JSON（省略時は results/ の最新）")
    parser.add_argument("--show", type=int, default=0, help="束ごとに実際の文をこの件数まで出す")
    parser.add_argument("--all-trials", action="store_true",
                        help="失敗した試行だけでなく全試行を対象にする")
    parser.add_argument("--first-half", action="store_true",
                        help="各試行の前半だけを見る（後半は出題者の意図を推し量る方向に転じるため）")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    if args.path:
        path = Path(args.path)
    else:
        files = sorted((BASE_DIR / "results").glob("run_*.json"))
        if not files:
            raise SystemExit("結果ファイルが見つかりません")
        path = files[-1]
    with open(path, encoding="utf-8") as f:
        run = json.load(f)

    if not any(x.get("thinking_chars") for x in run["results"]):
        raise SystemExit(
            f"{path.name} には思考テキストが入っていません。"
            "reasoning_content か <think> を返すモデルの結果が要ります。"
        )

    print(f"source: {path}")
    print(f"model: {', '.join(run['models'])} / suite: {run.get('suite')} / "
          f"prompt: {run.get('prompt_set')}")
    print(f"入力の指紋: {run['fingerprint']['inputs']}")
    print()

    rows = collect(run, failed_only=not args.all_trials, first_half=args.first_half)
    print(f"1. 抽出 — 「欠けている」と述べた文: {len(rows)} 件"
          f"（{'失敗した試行のみ' if not args.all_trials else '全試行'}"
          f"{'・各試行の前半のみ' if args.first_half else ''}）")
    print(f"   使った正規表現: {MISSING.pattern}")
    print()

    counts = Counter(bucket(s) for _, _, _, s in rows)
    print("2. 束ね — どのフィールドが無いと言っているか")
    for name, _, _ in BUCKETS:
        print(f"   {name:<24}{counts.get(name, 0):>4} 件")
    print(f"   {'(分類できず)':<24}{counts.get(None, 0):>4} 件")
    print()

    print("3. 書き出し — 逆算された要求仕様")
    for name, _, _ in BUCKETS:
        if counts.get(name):
            print(f"   * {requirement_text(name)}  （根拠 {counts[name]} 件）")
    print()

    if args.show:
        print("   根拠の文（そのまま）")
        for name, _, _ in BUCKETS:
            picked = [r for r in rows if bucket(r[3]) == name][: args.show]
            if not picked:
                continue
            print(f"   [{name}]")
            for condition, task, attempt, s in picked:
                print(f"     ({condition} / {task} / 試行{attempt}) {s}")
        print()

    print("4. 確認 — 書き足した水準で言及が消えるか（抽出器は 1 と同じ）")
    print(f"   {'水準':<20}{'正答':<8}{'思考字数':<12}{'言及'}")
    for row in verify(run):
        print(f"   {row['condition']:<20}{row['solved']}/{row['trials']:<6}"
              f"{row['thinking_chars']:<12,}{row['mentions']}")


if __name__ == "__main__":
    main()
