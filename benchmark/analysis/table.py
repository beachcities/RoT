"""全実行を1行ずつ、総トークン順に並べた表を出す。

分布の形から群を推定するのではなく、個々の実行が何をしていたかを目で追うための表。
markdown と csv の両方を出す（csvは utf-8-sig。Excelでそのまま開けるように）。
"""

import csv
import os

from dataset import load_runs, OUT_DIR

TABLE_DIR = os.path.join(OUT_DIR, "tables")
HEAD_CHARS = 60

COLUMNS = [
    ("rank", "順位"),
    ("run_id", "run"),
    ("condition", "水準"),
    ("task_id", "タスク"),
    ("repeat", "反復"),
    ("attempts", "試行"),
    ("cap", "上限到達"),
    ("correct", "正答"),
    ("prompt_tokens", "入力"),
    ("completion_tokens", "生成"),
    ("reasoning_tokens", "CoT"),
    ("total_tokens", "総"),
    ("answer_head", "応答の冒頭"),
]


def _head(text):
    flat = " ".join((text or "").split())
    if len(flat) > HEAD_CHARS:
        flat = flat[:HEAD_CHARS] + "…"
    return flat.replace("|", "／")


def build_rows(rows):
    ordered = sorted(rows, key=lambda r: (-(r["total_tokens"] or 0), r["run_id"], r["condition"]))
    out = []
    for i, r in enumerate(ordered, 1):
        out.append(
            {
                "rank": i,
                "run_id": r["run_id"],
                "condition": r["condition"],
                "task_id": r["task_id"],
                "repeat": r["repeat"],
                "attempts": r["attempts"],
                "cap": "yes" if r["hit_cap"] else "",
                "correct": "o" if r["success"] else "x",
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "reasoning_tokens": "n/a" if r["reasoning_tokens"] is None else r["reasoning_tokens"],
                "total_tokens": r["total_tokens"],
                "answer_head": _head(r["final_answer"]),
                "latency_sec": r["latency_sec"],
                "status": r["status"],
            }
        )
    return out


def write_markdown(table, path):
    keys = [k for k, _ in COLUMNS]
    labels = [f"{k}<br>{ja}" for k, ja in COLUMNS]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 全実行（1行 = 1試行）を総トークン降順に並べた表\n\n")
        fh.write("`results/` の v3_levels 実測run（mockを除く）を全部。要約はしていない。\n")
        fh.write("`試行` は同一会話内のリトライ回数、`反復` は会話を捨てた独立標本の番号。\n")
        fh.write("`CoT` は API が reasoning_tokens を返した場合のみ。gpt-4o-mini は常に 0 を返す。\n\n")
        fh.write("| " + " | ".join(labels) + " |\n")
        fh.write("|" + "|".join(["---"] * len(keys)) + "|\n")
        for row in table:
            fh.write("| " + " | ".join(str(row[k]) for k in keys) + " |\n")


def write_csv(table, path):
    keys = [k for k, _ in COLUMNS] + ["latency_sec", "status"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for row in table:
            w.writerow({k: row[k] for k in keys})


def main():
    os.makedirs(TABLE_DIR, exist_ok=True)
    _, rows = load_runs()
    table = build_rows(rows)
    write_markdown(table, os.path.join(TABLE_DIR, "all_trials_by_tokens.md"))
    write_csv(table, os.path.join(TABLE_DIR, "all_trials_by_tokens.csv"))
    print("rows:", len(table))


if __name__ == "__main__":
    main()
