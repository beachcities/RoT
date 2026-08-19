"""図を読むときに手元に置いておく素の数え上げ。

検定はしない。分布の当てはめもしない。数えるだけ、並べるだけ。
"""

import os
from collections import Counter, defaultdict

from dataset import load_runs, levels_in, OUT_DIR

TABLE_DIR = os.path.join(OUT_DIR, "tables")


def main():
    os.makedirs(TABLE_DIR, exist_ok=True)
    runs, rows = load_runs()
    out = []
    w = out.append

    w("# 数え上げ（図を読むための素の数字）\n")
    w("検定はしていない。分布の当てはめもしていない。数えて並べただけ。\n")

    w("\n## 1. run の一覧\n")
    w("| run | 反復数 | 水準数 | 試行数 | max_attempts | prompt_set | model |")
    w("|---|---|---|---|---|---|---|")
    for m in runs:
        w("| %s | %s | %d | %d | %s | %s | %s |" % (
            m["run_id"], m["repeats"], len(m["conditions"]), m["n_trials"],
            m["max_attempts"], m["prompt_set"], ",".join(m["models"] or [])))

    w("\n## 2. run × 水準ごとの試行回数の内訳\n")
    w("`試行回数の内訳` は「その回数で終わった試行が何本あったか」。10 は上限到達（=解けなかった）。\n")
    w("| run | 水準 | n | 正答 | 総トークン min | max | 試行回数の内訳 |")
    w("|---|---|---|---|---|---|---|")
    for m in runs:
        for c in levels_in(rows, m["run_id"]):
            sub = [r for r in rows if r["run_id"] == m["run_id"] and r["condition"] == c]
            att = Counter(r["attempts"] for r in sub)
            breakdown = " ".join("%d回:%d" % (k, att[k]) for k in sorted(att))
            w("| %s | %s | %d | %d | %d | %d | %s |" % (
                m["run_id"], c, len(sub), sum(1 for r in sub if r["success"]),
                min(r["total_tokens"] for r in sub), max(r["total_tokens"] for r in sub), breakdown))

    w("\n## 3. 試行回数ごとの総トークン（全run・全水準をまとめて）\n")
    w("同じ試行回数の中で総トークンがどれだけ散るか。`max/min` が小さいほど、")
    w("消費が試行回数だけでほぼ決まっていることになる。\n")
    w("| 試行回数 | n | min | median | max | max/min | 水準の内訳 |")
    w("|---|---|---|---|---|---|---|")
    by_att = defaultdict(list)
    for r in rows:
        by_att[r["attempts"]].append(r)
    for a in sorted(by_att):
        tt = sorted(r["total_tokens"] for r in by_att[a])
        med = tt[len(tt) // 2] if len(tt) % 2 else (tt[len(tt) // 2 - 1] + tt[len(tt) // 2]) / 2
        conds = Counter(r["condition"] for r in by_att[a])
        w("| %d | %d | %d | %.0f | %d | %.2f | %s |" % (
            a, len(tt), tt[0], med, tt[-1], tt[-1] / tt[0],
            " ".join("%s:%d" % (k, v) for k, v in sorted(conds.items()))))

    w("\n## 4. l2_units_ref の全点を昇順に並べる（n=15 の run と n=30 の run）\n")
    for run_id in ("222907Z", "224435Z"):
        sub = sorted((r for r in rows if r["run_id"] == run_id and r["condition"] == "l2_units_ref"),
                     key=lambda r: r["total_tokens"])
        if not sub:
            continue
        n = len(sub)
        mid = [n // 2] if n % 2 else [n // 2 - 1, n // 2]
        w("\n### run %s  (n=%d)\n" % (run_id, n))
        w("| # | 総トークン | 試行 | 正答 | タスク | 反復 | 中央値の位置 |")
        w("|---|---|---|---|---|---|---|")
        for i, r in enumerate(sub):
            w("| %d | %d | %d | %s | %s | %s | %s |" % (
                i + 1, r["total_tokens"], r["attempts"], "o" if r["success"] else "x",
                r["task_id"], r["repeat"], "<-- ここ" if i in mid else ""))

    w("\n## 5. 水準そのものの大きさ（1試行目の入力トークン）\n")
    w("同じ (水準, タスク) なら1試行目の入力トークンは全runで完全に一致する。プロンプトも入力データも")
    w("固定だからで、ここには散らばりがない。水準の「自己記述の量」はこの列にそのまま出ている。\n")
    w("| 水準 | task_01 | task_02 | task_03 | 1試行目の生成トークン n / min / 中央 / max |")
    w("|---|---|---|---|---|")
    first_prompt = defaultdict(dict)
    first_comp = defaultdict(list)
    for r in rows:
        if r["attempt_prompts"]:
            first_prompt[r["condition"]][r["task_id"]] = r["attempt_prompts"][0]
        if r["first_completion"]:
            first_comp[r["condition"]].append(r["first_completion"])
    for c in levels_in(rows):
        fp = first_prompt.get(c, {})
        fc = sorted(first_comp.get(c, []))
        w("| %s | %s | %s | %s | %d / %d / %d / %d |" % (
            c, fp.get("task_01", "-"), fp.get("task_02", "-"), fp.get("task_03", "-"),
            len(fc), fc[0], fc[len(fc) // 2], fc[-1]))

    w("\n## 6. 内訳フィールドの中身\n")
    rt = Counter(str(r["reasoning_tokens"]) for r in rows)
    ot = Counter(str(r["output_tokens"]) == str(r["completion_tokens"]) for r in rows)
    w("- `reasoning_tokens` の値の分布: %s" % dict(rt))
    w("- `output_tokens == completion_tokens` の件数: %s" % dict(ot))
    w("- `status` の分布: %s" % dict(Counter(r["status"] for r in rows)))
    w("- `tokens_measured` の分布: %s" % dict(Counter(str(r["tokens_measured"]) for r in rows)))
    w("- 正答しなかった試行のうち、試行回数が上限(10)だったものの割合: %d / %d" % (
        sum(1 for r in rows if not r["success"] and r["hit_cap"]),
        sum(1 for r in rows if not r["success"])))
    w("- 正答した試行のうち、試行回数が上限(10)だったもの: %d 件" % (
        sum(1 for r in rows if r["success"] and r["hit_cap"])))

    path = os.path.join(TABLE_DIR, "counts.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
