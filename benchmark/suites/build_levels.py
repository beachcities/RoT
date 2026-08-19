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
]

CODE_NAMES = {101: "情報通信業", 201: "食料品製造業", 202: "金属製品製造業"}

TASKS = json.loads((BASE / "v2d_tax" / "tasks.json").read_text(encoding="utf-8"))

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
    (OUT / "conditions.json").write_text(
        json.dumps({"conditions": conditions}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "tasks.json").write_text(
        json.dumps(TASKS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} ({len(conditions)} 水準)")


if __name__ == "__main__":
    main()
