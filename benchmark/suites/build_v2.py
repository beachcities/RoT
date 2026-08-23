# -*- coding: utf-8 -*-
"""v2 系の組を書き出す。

すべての組が**同じ世界・同じタスク**を共有し、raw 側に置く手がかりだけが違う。
そう作らないと、組の間で raw 側の正答率を比べても、手がかりの効果なのか
世界が違うせいなのかが分からない。

    python suites/build_v2.py

self_descriptive 側は常に同じ世界を、単位も定義も名前も明示した形で書く。
"""

import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parent

# 会計年度2024 = 2024-04-01 〜 2025-03-31。廃業日はこの期間内に置く。
# 期首前に廃業した企業が当年度の売上を持っていると、データ自体が不整合になり、
# self_descriptive 側でも解けなくなる（実測で確認した）。
CORE = [
    dict(id="org_001", cd=101, nm="Alpha Systems",        ind="情報通信業",           emp=40,  cap=90_000_000,  val=1200, end=None),
    dict(id="org_002", cd=201, nm="Beta Foods",           ind="食料品製造業",         emp=120, cap=50_000_000,  val=850,  end="2024-11-30"),
    dict(id="org_003", cd=101, nm="Gamma Networks",       ind="情報通信業",           emp=15,  cap=10_000_000,  val=430,  end="2024-06-30"),
    dict(id="org_004", cd=202, nm="Delta Metal Works",    ind="金属製品製造業",       emp=310, cap=200_000_000, val=2750, end=None),
    dict(id="org_005", cd=101, nm="Epsilon Data Service", ind="情報通信業",           emp=25,  cap=30_000_000,  val=660,  end=None),
]

# v2c_anchor は取り下げた。外部の常識で桁が確かめられる実在企業を1件混ぜる設計で、
# 実在企業の従業員数と売上高を合成企業と同じ配列に並べる形になっていた。数値自体は
# 公開情報だが、合成データと同列に置くと、そのレコードも合成だと読まれるか、逆に
# 他のレコードも実在だと読まれる。公開リポジトリに置く形として適切でないので、
# データも生成コードも消してある。何をしていた組かは README に残した。
TASKS = [
    dict(task_id="task_01",
         query="情報通信業に属し、かつ現在も活動中の企業について、2024年度の売上高の合計は何円ですか。単位を「円」に換算し、数値のみを答えてください。",
         ground_truth="1860000000",
         note="raw では cd=101 が情報通信業であること、活動中の判別、val_24 の単位の三つを推し量る必要がある"),
    dict(task_id="task_02",
         query="金属製品製造業に属し、かつ現在も活動中の企業について、2024年度の売上高は何円ですか。単位を「円」に換算し、数値のみを答えてください。",
         ground_truth="2750000000",
         note="raw では cd=202 が金属製品製造業であることを社名から推す必要がある"),
    # 当初は「廃業した企業の売上高の合計」を問うていたが、self_descriptive 側でも
    # 3回とも外した（1110/1210/220 など、単純和にならない値を返す）。廃業時期と
    # 年度の関係を絡めた問いは、条件の差とは別の failure mode を持ち込む。
    dict(task_id="task_03",
         query="食料品製造業に属する企業について、2024年度の売上高は何円ですか。単位を「円」に換算し、数値のみを答えてください。",
         ground_truth="850000000",
         note="raw では cd=201 が食料品製造業であることを社名から推す必要がある"),
]

# 手がかりの組み合わせ。cap と tax と anchor だけが違う。
VARIANTS = {
    "v2a_emp":     dict(cap=False, tax=False),
    "v2b_emp_cap": dict(cap=True,  tax=False),
    "v2d_tax":     dict(cap=True,  tax=True),
}

TAX_RATE = 0.10


def tax_yen(record):
    """消費税額（円）。売上（百万円）× 100万 × 10%。

    raw 側では単位を書かないかわりに、円建てのこの額と val_24 の比が
    ちょうど 100000 になる。比に気づけば単位が一意に決まる、という手がかり。
    """
    return int(record["val"] * 1_000_000 * TAX_RATE)


def raw_record(r, cfg):
    d = {"id": r["id"], "cd": r["cd"], "nm": r["nm"], "emp": r["emp"]}
    if cfg["cap"]:
        d["cap"] = r["cap"]
    d["val_24"] = r["val"]
    if cfg["tax"]:
        d["tax_24"] = tax_yen(r)
    d["flg"] = "N" if r["end"] else "Y"
    d["end_dt"] = r["end"]
    return d


def sd_record(r, cfg):
    d = {
        "corporate_id": r["id"],
        "industry_code": r["cd"],
        "industry_name": r["ind"],
        "company_name": r["nm"],
        "employee_count": r["emp"],
    }
    if cfg["cap"]:
        d["capital_stock_yen"] = r["cap"]
    d["fiscal_year_2024_revenue_million_yen"] = r["val"]
    if cfg["tax"]:
        d["fiscal_year_2024_consumption_tax_yen"] = tax_yen(r)
    d["is_active_entity"] = r["end"] is None
    d["closure_date"] = r["end"]
    return d


def sd_doc(records, cfg):
    units = {"fiscal_year_2024_revenue_million_yen": "百万円（税抜）", "employee_count": "人"}
    if cfg["cap"]:
        units["capital_stock_yen"] = "円"
    if cfg["tax"]:
        units["fiscal_year_2024_consumption_tax_yen"] = "円"
    return {
        "$schema": "https://example.gov/schemas/corp_activity_v2.json",
        "description": "2024年度 企業活動実態調査データ（会計年度 2024-04-01〜2025-03-31）",
        "unit_definition": units,
        "field_definition": {
            "industry_code": "日本標準産業分類に準拠した内部コード",
            "industry_name": "industry_code に対応する業種名",
            "is_active_entity": "調査基準日（2025-03-31）時点で事業活動を継続しているか",
            "closure_date": "廃業した場合はその日付。活動を継続している場合は null",
        },
        "records": [sd_record(r, cfg) for r in records],
    }


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    for name, cfg in VARIANTS.items():
        records = CORE
        d = BASE / name
        d.mkdir(parents=True, exist_ok=True)
        write(d / "raw_dataset.json", [raw_record(r, cfg) for r in records])
        write(d / "self_descriptive_dataset.json", sd_doc(records, cfg))
        write(d / "tasks.json", TASKS)
        print("wrote", d)


if __name__ == "__main__":
    main()
