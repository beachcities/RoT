"""全実行を1行ずつ、総トークン順に並べた表を出す。

分布の形から群を推定するのではなく、個々の実行が何をしていたかを目で追うための表。
markdown と csv の両方を出す（csvは utf-8-sig。Excelでそのまま開けるように）。

対象の run は RUNS に固定してある。`results/` を走査したままにすると、走らせるたびに
表の中身が変わり、OBSERVATIONS.md が指している対象とずれるため。別の run で作るときは
--runs で明示的に指定する。

応答本文は載せない。理由は BODY_NOTE を参照。
"""

import csv
import os

from dataset import load_runs, OUT_DIR

TABLE_DIR = os.path.join(OUT_DIR, "tables")

# OBSERVATIONS.md が対象にしている3本。既定ではこれだけを表にする。
RUNS = ("220208Z", "222907Z", "224435Z")

BODY_NOTE = """> **応答本文は載せていない。** 以前の版にはモデルの応答の冒頭60字を入れていたが、
> ここに並ぶ3本は参照点として扱わないと決めたランであり、本文を公開する方針
> （参照点1ランのみ本文つき）と食い違うため、列ごと落とした。
> 数値・水準・タスク・反復・試行回数・正誤は残してある。
> 応答本文が要る場合は、その run の結果JSONの `attempt_log[].answer` を直接見ること。
> なお、落としたのは現在の版であって、リポジトリの履歴には以前の版が残っている。"""

# csv の1行目に入れる注記。読み込む側は読み飛ばす前提（pandas なら comment="#"）。
CSV_NOTE = (
    "# 応答本文の列は落としてある。対象3本は参照点として扱わないランで、"
    "本文の公開方針と食い違うため。詳細は all_trials_by_tokens.md の注記を参照。"
    "この行は注記なので、読み込むときは読み飛ばすこと。"
)

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
]


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
        fh.write("対象は %s の3本。要約はしていない。\n" % "・".join(RUNS))
        fh.write("`試行` は同一会話内のリトライ回数、`反復` は会話を捨てた独立標本の番号。\n")
        fh.write("`CoT` は API が reasoning_tokens を返した場合のみ。gpt-4o-mini は常に 0 を返す。\n\n")
        fh.write(BODY_NOTE + "\n\n")
        fh.write("| " + " | ".join(labels) + " |\n")
        fh.write("|" + "|".join(["---"] * len(keys)) + "|\n")
        for row in table:
            fh.write("| " + " | ".join(str(row[k]) for k in keys) + " |\n")


def write_csv(table, path):
    keys = [k for k, _ in COLUMNS] + ["latency_sec", "status"]
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        # 1行目は注記。読み込むときは読み飛ばすこと（pandas なら comment="#"）。
        fh.write(CSV_NOTE + "\r\n")
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for row in table:
            w.writerow({k: row[k] for k in keys})


def main(run_ids=RUNS):
    os.makedirs(TABLE_DIR, exist_ok=True)
    _, rows = load_runs()
    if run_ids:
        rows = [r for r in rows if r["run_id"] in set(run_ids)]
    table = build_rows(rows)
    write_markdown(table, os.path.join(TABLE_DIR, "all_trials_by_tokens.md"))
    write_csv(table, os.path.join(TABLE_DIR, "all_trials_by_tokens.csv"))
    print("rows:", len(table), "runs:", ",".join(run_ids) if run_ids else "(all)")


if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    if args and args[0] == "--runs":
        main(tuple(args[1].split(",")))
    else:
        main()
