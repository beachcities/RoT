# -*- coding: utf-8 -*-
"""自己記述性を10段階に刻んだ組を書き出す。

    python suites/build_levels.py

同じ世界・同じタスクを10通りの書き方で表す。段は**仮の刻み**であって、検証
すべき仮説ではない。消費が段に沿って動くかを見るための足場として置いている。

二つの軸を混ぜて振ってある。

* 書き方の軸: 何も書かない → 項目名を意味のある語にする → 単位を明示する
  → コード・列挙値の意味を明示する
* 参照の距離の軸: 同じレコード内に置く / 文書のヘッダに置く / 外部への参照
  だけを張って本体には書かない

直交しない組み合わせは作っていない（単位を書かずにコードの意味だけ書く、など）。

文書の構造はどの段でも同じ（`records` を持つオブジェクト）にしてある。段の間で
構造まで変えると、消費の差が構造の差なのか記述の差なのか分からなくなるため。
"""

import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parent
OUT = BASE / "v3_levels"

SCHEMA_URL = "https://example.gov/schemas/corp_activity_v3.json"
CODE_LIST_URL = "https://example.gov/codes/jsic_internal_v1.json"

CORE = [
    dict(id="org_001", cd=101, nm="Alpha Systems",        ind="情報通信業",     emp=40,  cap=90_000_000,  val=1200, end=None),
    dict(id="org_002", cd=201, nm="Beta Foods",           ind="食料品製造業",   emp=120, cap=50_000_000,  val=850,  end="2024-11-30"),
    dict(id="org_003", cd=101, nm="Gamma Networks",       ind="情報通信業",     emp=15,  cap=10_000_000,  val=430,  end="2024-06-30"),
    dict(id="org_004", cd=202, nm="Delta Metal Works",    ind="金属製品製造業", emp=310, cap=200_000_000, val=2750, end=None),
    dict(id="org_005", cd=101, nm="Epsilon Data Service", ind="情報通信業",     emp=25,  cap=30_000_000,  val=660,  end=None),
    # ここから下は社名から業種が推せない企業。cd の意味は書いてある段でしか分からない。
    # 的（問われる2業種）を当て推量で見つけられないよう、識別子を潰してある。
    # 何を潰したかは CLUES.md の「識別子の列挙」を参照。
    #   * 推せないコード6つすべてを2社ずつにする（所属企業数が識別子にならない）
    #   * 的は 707（5番目）と 505（3番目）。先頭2つではなく、問いで挙げる順
    #     （専門サービス業→学術研究業）とコードの昇順も一致しない
    #   * 群の従業員合計は 130/81/125/83/103/117。的（125, 103）は最大でも最小でもない
    #   * 推せない社名の企業はすべて廃業。活動状態が的の識別子にならない
    dict(id="org_006", cd=303, nm="Zeta Holdings",      ind="娯楽業",             emp=78, cap=20_000_000, val=910,  end="2024-08-31"),
    dict(id="org_007", cd=303, nm="Eta Partners",       ind="娯楽業",             emp=52, cap=15_000_000, val=620,  end="2024-10-15"),
    dict(id="org_008", cd=404, nm="Theta Group",        ind="不動産業",           emp=63, cap=25_000_000, val=780,  end="2024-05-20"),
    dict(id="org_009", cd=404, nm="Iota Associates",    ind="不動産業",           emp=18, cap=12_000_000, val=540,  end="2024-06-15"),
    dict(id="org_010", cd=505, nm="Kappa Corporation",  ind="学術研究業",         emp=72, cap=18_000_000, val=460,  end="2024-07-10"),
    dict(id="org_011", cd=505, nm="Lambda Enterprises", ind="学術研究業",         emp=53, cap=22_000_000, val=1340, end="2024-09-05"),
    dict(id="org_012", cd=606, nm="Mu Ventures",        ind="卸売業",             emp=47, cap=8_000_000,  val=310,  end="2024-12-01"),
    dict(id="org_013", cd=606, nm="Nu Company",         ind="卸売業",             emp=36, cap=30_000_000, val=1120, end="2024-04-18"),
    dict(id="org_014", cd=707, nm="Xi Group",           ind="専門サービス業",     emp=55, cap=16_000_000, val=700,  end="2024-11-22"),
    dict(id="org_015", cd=707, nm="Omicron Partners",   ind="専門サービス業",     emp=48, cap=11_000_000, val=580,  end="2024-05-09"),
    dict(id="org_016", cd=808, nm="Pi Associates",      ind="生活関連サービス業", emp=90, cap=27_000_000, val=990,  end="2024-09-28"),
    dict(id="org_017", cd=808, nm="Rho Holdings",       ind="生活関連サービス業", emp=27, cap=9_000_000,  val=350,  end="2024-07-31"),
]

CODE_NAMES = {101: "情報通信業", 201: "食料品製造業", 202: "金属製品製造業",
              303: "娯楽業", 404: "不動産業", 505: "学術研究業",
              606: "卸売業", 707: "専門サービス業", 808: "生活関連サービス業"}

# 社名から業種が推せる企業と、推せない企業。タスクの分類の根拠になるので明示する。
GUESSABLE_CODES = {101, 201, 202}
OPAQUE_CODES = {303, 404, 505, 606, 707, 808}

UNIT_SUFFIX = "単位を「円」に換算し、数値のみを答えてください。"
COUNT_SUFFIX = "数値のみを答えてください。"

# タスクは2群ある。
#   単位群（task_01〜03）: 正答に単位（百万円）の解決が要る。
#   非単位群（task_04〜06）: 従業員数を数えるだけで、単位の換算は要らない。
#     そのかわり、業種コードや活動フラグの意味が要る。上位段に境界が出るかを
#     見るためのもの。単位を同時に要求すると l2/l3 の境界に埋もれる。
TASKS = [
    dict(task_id="task_01", group="unit",
         query="情報通信業に属し、かつ現在も活動中の企業について、2024年度の売上高の合計は何円ですか。" + UNIT_SUFFIX,
         ground_truth="1860000000",
         needs="単位。業種は社名から推せる"),
    dict(task_id="task_02", group="unit",
         query="金属製品製造業に属し、かつ現在も活動中の企業について、2024年度の売上高は何円ですか。" + UNIT_SUFFIX,
         ground_truth="2750000000",
         needs="単位。業種は社名から推せる"),
    dict(task_id="task_03", group="unit",
         query="食料品製造業に属する企業について、2024年度の売上高は何円ですか。" + UNIT_SUFFIX,
         ground_truth="850000000",
         needs="単位。業種は社名から推せる"),
    dict(task_id="task_04", group="code_guessable",
         query="情報通信業に属する企業について、従業員数の合計は何人ですか。" + COUNT_SUFFIX,
         ground_truth="80",
         needs="業種コードの意味。ただし社名（Systems / Networks / Data Service）から推せる"),
    dict(task_id="task_05", group="flag",
         query="現在も活動を継続している企業について、従業員数の合計は何人ですか。" + COUNT_SUFFIX,
         ground_truth="375",
         needs="列挙値の意味（活動状態）。ただし廃業日の有無からも推せる"),
    # 2業種の合計を問う。単一業種だと、見えている cd の値でコード群を列挙して
    # 上限10試行の総当たりで当たってしまう。
    dict(task_id="task_06", group="code_opaque",
         query="専門サービス業と学術研究業に属する企業について、従業員数の合計は何人ですか。" + COUNT_SUFFIX,
         ground_truth="228",
         needs="業種コード 303 と 404 の意味。どちらも社名からは推せず、消去法でも辿れない"),
]

# タスクの分類。「手がかりがあれば書かれていなくても済む」ことを示す対照として、
# 逃げ道を持つタスクを意図的に残してある。どれが逃げ道を持つかを明示する。
TASK_ESCAPE_ROUTES = {
    "task_01": {"escapable": True,
                "route": "業種は社名（Systems / Networks / Data Service）から推せる。単位は推せない"},
    "task_02": {"escapable": True, "route": "業種は社名（Metal Works）から推せる。単位は推せない"},
    "task_03": {"escapable": True, "route": "業種は社名（Foods）から推せる。単位は推せない"},
    "task_04": {"escapable": True, "route": "業種を社名から推せる。単位は不要"},
    "task_05": {"escapable": True,
                "route": "活動状態は廃業日フィールドの有無から推せる。列挙値の意味は不要"
                         "（推せない社名の企業をすべて廃業にしたため、正答は 430 から 375 に変わった）"},
    "task_06": {"escapable": False,
                "route": "社名から推せない業種が6コード、各2社ずつ。消去法・並び順・"
                         "所属企業数・レコード順・群の規模・活動状態のいずれからも的を"
                         "特定できない。候補は C(6,2)=15 通りで上限10試行では尽くせない"},
}

# 段の定義。値がそのまま conditions.json に入り、結果JSONにも残る。
#   naming    : opaque    項目名が意味を持たない / meaningful 意味のある語
#   units     : none / external 外部参照のみ / document ヘッダ / record レコード内
#   codes     : none / external / document / record   （業種コードの意味）
#   flags     : code      Y/N のまま      / record 真偽値としてレコード内
#   prose     : none / document           （項目そのものの説明文）
LEVELS = [
    ("l0_opaque",       dict(naming="opaque",     units="none",     codes="none",     flags="code",   prose="none")),
    ("l1_names",        dict(naming="meaningful", units="none",     codes="none",     flags="code",   prose="none")),
    ("l2_units_ref",    dict(naming="meaningful", units="external", codes="none",     flags="code",   prose="none")),
    ("l3_units_doc",    dict(naming="meaningful", units="document", codes="none",     flags="code",   prose="none")),
    ("l4_units_record", dict(naming="meaningful", units="record",   codes="none",     flags="code",   prose="none")),
    ("l5_codes_ref",    dict(naming="meaningful", units="record",   codes="external", flags="code",   prose="none")),
    ("l6_codes_doc",    dict(naming="meaningful", units="record",   codes="document", flags="code",   prose="none")),
    ("l7_codes_record", dict(naming="meaningful", units="record",   codes="record",   flags="code",   prose="none")),
    ("l8_flags_record", dict(naming="meaningful", units="record",   codes="record",   flags="record", prose="none")),
    ("l9_prose",        dict(naming="meaningful", units="record",   codes="record",   flags="record", prose="document")),
]

OPAQUE = dict(id="id", code="cd", name="nm", emp="emp", cap="cap",
              val="val_24", tax="tax_24", flag="flg", end="end_dt")
PLAIN = dict(id="corporate_id", code="industry_code", name="company_name",
             emp="employee_count", cap="capital_stock", val="revenue_2024",
             tax="consumption_tax_2024", flag="activity_status", end="closure_date")
WITH_UNITS = dict(PLAIN, emp="employee_count_persons", cap="capital_stock_yen",
                  val="revenue_2024_million_yen", tax="consumption_tax_2024_yen")


def field_names(spec):
    if spec["naming"] == "opaque":
        return OPAQUE
    return WITH_UNITS if spec["units"] == "record" else PLAIN


def record(r, spec):
    f = field_names(spec)
    d = {f["id"]: r["id"], f["code"]: r["cd"]}
    if spec["codes"] == "record":
        d["industry_name"] = r["ind"]
    d[f["name"]] = r["nm"]
    d[f["emp"]] = r["emp"]
    d[f["cap"]] = r["cap"]
    d[f["val"]] = r["val"]
    d[f["tax"]] = int(r["val"] * 1_000_000 * 0.10)
    if spec["flags"] == "record":
        d["is_active_entity"] = r["end"] is None
        d["closure_date"] = r["end"]
    else:
        d[f["flag"]] = "N" if r["end"] else "Y"
        d[f["end"]] = r["end"]
    return d


def document(spec):
    doc = {}
    if spec["units"] == "external":
        doc["$schema"] = SCHEMA_URL
        doc["unit_reference"] = "各項目の単位は上記スキーマ定義を参照のこと"
    if spec["units"] == "document":
        doc["unit_definition"] = {
            PLAIN["val"]: "百万円（税抜）",
            PLAIN["tax"]: "円",
            PLAIN["cap"]: "円",
            PLAIN["emp"]: "人",
        }
    if spec["codes"] == "external":
        doc["code_list_reference"] = CODE_LIST_URL
    if spec["codes"] == "document":
        doc["code_definition"] = {str(k): v for k, v in CODE_NAMES.items()}
    if spec["prose"] == "document":
        doc["description"] = "2024年度 企業活動実態調査データ（会計年度 2024-04-01〜2025-03-31）"
        doc["field_definition"] = {
            "industry_code": "日本標準産業分類に準拠した内部コード",
            "industry_name": "industry_code に対応する業種名",
            "is_active_entity": "調査基準日（2025-03-31）時点で事業活動を継続しているか",
            "closure_date": "廃業した場合はその日付。活動を継続している場合は null",
        }
    doc["records"] = [record(r, spec) for r in CORE]
    return doc


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    conditions = []
    for name, spec in LEVELS:
        filename = f"{name}.json"
        (OUT / filename).write_text(
            json.dumps(document(spec), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        conditions.append({"name": name, "file": filename, "level": len(conditions), "placed": spec})
    for task in TASKS:
        task["escape_route"] = TASK_ESCAPE_ROUTES[task["task_id"]]
    (OUT / "conditions.json").write_text(
        json.dumps({"conditions": conditions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "tasks.json").write_text(
        json.dumps(TASKS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} ({len(conditions)} 水準)")


if __name__ == "__main__":
    main()
