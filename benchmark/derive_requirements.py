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
# 「無い」と述べている引き金。文全体ではなく、この語句の位置を手がかりにする。
MISSING = re.compile(
    r"(?:doesn't|does not|didn't|did not) (?:list|have|specify|provide|include|define|contain)"
    r"|(?:isn't|is not|aren't|are not|wasn't) (?:provided|specified|given|available|included|defined|listed)"
    r"|no (?:explicit|clear)? ?(?:mapping|label|labels|definition|definitions|key)"
    r"|lack(?:s|ing)? (?:of )?(?:a )?(?:clear |explicit )?(?:mapping|definition|labels?)",
    re.I,
)

# 引き金の直前にある主語。ここで「何が欠けていると言っているか」の対象が決まる。
#
# **問いや出題者を主語にした文は落とす。** 「the question doesn't specify whether to
# include closed companies」は課題の曖昧さであって、データ側の欠落ではない。
# これを混ぜると、要求仕様にならない文が束に入る（実測: 101文中27文がこれだった）。
SUBJECT_QUESTION = re.compile(
    r"(?:the )?(?:question|problem statement|prompt|user|they|task)\s*$", re.I)
# データを主語にした文だけを採る。「it」は直前の文を受けるので採らない。
SUBJECT_DATA = re.compile(
    r"(?:data|dataset|records?|schema|json|file|table|fields?|entries|"
    r"unit_definition|code_definition|情報|データ)\W*$", re.I)

SUBJECT_WINDOW = 60      # 引き金の手前をどこまで遡って主語を探すか

# **記述の欠落だけを採る。** データに「その業種の企業が1件も入っていない」という話は、
# 中身についての観察であって、自己記述性の話ではない。要求仕様にならない
# （実測: 採った27文のうち11文がこれで、うち10文はどの束にも入らなかった）。
# 記述を指す語が文中にあることを条件にして、中身の話を落とす。
DOCUMENTATION = re.compile(
    r"label|definition|mapping|key|means?|stand(?:s)? for|explain|describ"
    r"|classification|what each|unit_definition|code_definition"
    r"|industry (?:type|name)s?"
    r"|意味|定義|対応表",
    re.I,
)


def sentence_around(text, pos):
    """引き金の位置を含む1文を切り出す。"""
    left = text.rfind(".", 0, pos) + 1
    right = text.find(".", pos)
    right = len(text) if right == -1 else right + 1
    return " ".join(text[left:right].split())


def classify_subject(text, pos):
    """引き金の直前を見て、何が「無い」と言われているかの主語を返す。"""
    head = text[max(0, pos - SUBJECT_WINDOW):pos]
    if SUBJECT_QUESTION.search(head):
        return "question"
    if SUBJECT_DATA.search(head):
        return "data"
    return "other"


def extract(thinking, keep=("data",)):
    """データ側の欠落を述べた文だけを返す。

    引き金（MISSING）を見つけ、その直前の主語で振り分ける。
    既定ではデータを主語にした文だけを採る。
    """
    out = []
    text = thinking or ""
    for m in MISSING.finditer(text):
        if classify_subject(text, m.start()) not in keep:
            continue
        sentence = sentence_around(text, m.start())
        if not DOCUMENTATION.search(sentence):
            continue
        if 40 <= len(sentence) <= 400:
            out.append(sentence)
    return out


def extract_all(thinking):
    """主語ごとの内訳。落とした文が何だったかを数えるために使う。"""
    counts = {"data": 0, "question": 0, "other": 0, "content_only": 0}
    text = thinking or ""
    for m in MISSING.finditer(text):
        kind = classify_subject(text, m.start())
        if kind == "data" and not DOCUMENTATION.search(sentence_around(text, m.start())):
            kind = "content_only"
        counts[kind] += 1
    return counts


# --- 2. 束ね -------------------------------------------------------------
# **先勝ちにしない。** 一致した数で採点し、最も多い束に入れる。
# 先勝ちにすると、たまたま先に並んでいる束の語が1つ入っただけで持っていかれる
# （実測: コードの意味が無いと述べた文が、"external" の一語で外部参照の束に入っていた）。
BUCKETS = [
    ("industry_code_meaning",
     re.compile(r"industry (?:type|code|classification|label|name)s?"
                r"|(?:code|cd)s? (?:to|-|→)? ?industr"
                r"|what (?:each|the) (?:industry |cd |code )?(?:code|cd)s? (?:means?|stand)"
                r"|industry (?:labels?|mapping)|labels? for (?:these |the )?industr"
                r"|(?:mapping|key) (?:of|for|between) .{0,20}(?:code|industr)"
                r"|code_definition|code_list|jsic|業種", re.I),
     "業種コードの意味（コード → 業種名の対応表）を、データ本体に書く"),
    ("unit",
     re.compile(r"\bunits?\b|million|currency|per (?:yen|dollar)|unit_definition|単位|百万", re.I),
     "数値の単位を、データ本体に書く"),
    ("activity_status",
     re.compile(r"(?:flg|flag|activity_status|is_active)\b"
                r"|what (?:'?Y'?|'?N'?) (?:means?|stands)"
                r"|(?:active|closed|closure) (?:status|flag|means?)"
                r"|活動状態|廃業", re.I),
     "活動状態の意味（列挙値が何を表すか）を、データ本体に書く"),
    ("external_reference",
     re.compile(r"\bschema\b|code_list_reference|https?://|external (?:code|list|file|reference)"
                r"|referenced? (?:file|document|url)", re.I),
     "外部参照の先にある定義を、データ本体に取り込む"),
]


def bucket(sentence):
    """一致数で採点して束を決める。同点なら BUCKETS の並び順で先のものを採る。"""
    best, best_score = None, 0
    for name, pattern, _ in BUCKETS:
        score = len(set(m.group(0).lower() for m in pattern.finditer(sentence)))
        if score > best_score:
            best, best_score = name, score
    return best


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
    tally = {"data": 0, "question": 0, "other": 0, "content_only": 0}
    for r in run["results"]:
        if not args.all_trials and r["success"]:
            continue
        for a in r["attempt_log"]:
            for k, v in extract_all(a.get("thinking")).items():
                tally[k] += v
    print(f"1. 抽出 — データ側の欠落を述べた文: {len(rows)} 件"
          f"（{'失敗した試行のみ' if not args.all_trials else '全試行'}"
          f"{'・各試行の前半のみ' if args.first_half else ''}）")
    print(f"   引き金の総数 {sum(tally.values())} 件の内訳:")
    print(f"     主語がデータ      {tally['data']:>4} 件  → 採る")
    print(f"     主語が問い/出題者 {tally['question']:>4} 件  → 落とす"
          f"（課題の曖昧さであってデータの欠落ではない）")
    print(f"     主語が判別できず  {tally['other']:>4} 件  → 落とす")
    print(f"     中身の話          {tally['content_only']:>4} 件  → 落とす"
          f"（「その業種の企業が入っていない」等。記述の欠落ではない）")
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
