"""結果JSONだけから、入力データの版を事後的に見分けられるかを調べる。

結果JSONには投入データ本体もそのハッシュも入っていない。そこで代わりに、
1試行目の入力トークン数を (条件, タスク) ごとに並べたものを「観測された指紋」として使う。
プロンプト全文と投入データが同じなら、この数は完全に一致するはずである。

これは本物の指紋の代わりにはならない。長さが変わらない改変（値の書き換え、同じ長さの語への
置換）はこの方法では検出できない。いま results/ にあるものを整理するための間に合わせ。
"""

import os
from collections import defaultdict

from dataset import load_runs, OUT_DIR

TABLE_DIR = os.path.join(OUT_DIR, "tables")


def fingerprint(rows, run_id):
    fp = {}
    for r in rows:
        if r["run_id"] != run_id or not r["attempt_prompts"]:
            continue
        fp[(r["condition"], r["task_id"])] = r["attempt_prompts"][0]
    return fp


def compatible(a, b):
    """共通する (条件, タスク) の値がすべて一致するか。共通が無ければ判定不能。"""
    shared = set(a) & set(b)
    if not shared:
        return None
    return all(a[k] == b[k] for k in shared)


def group_runs(order, fps):
    """互換なものを繋いでまとめる。互換の関係は推移的とは限らないので、あくまで目安。"""
    parent = {r: r for r in order}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if compatible(fps[a], fps[b]):
                parent[find(b)] = find(a)
    groups = defaultdict(list)
    for r in order:
        groups[find(r)].append(r)
    return [groups[k] for k in sorted(groups, key=lambda k: order.index(k))]


def main():
    os.makedirs(TABLE_DIR, exist_ok=True)
    runs, rows = load_runs(suite=None)
    out = []
    w = out.append

    w("# 観測された入力指紋（結果JSONだけから作れる範囲で）\n")
    w("結果JSONには投入データ本体もハッシュも入っていない。代わりに、1試行目の入力トークン数を")
    w("(条件, タスク) ごとに並べたものを指紋として使う。プロンプト全文と投入データが同じなら、")
    w("この数は完全に一致するはずである。プロンプトを言い換えた run（`p2_plain` / `p3_terse`）も")
    w("この指紋では別物になる。指紋はプロンプトと投入データを合わせたものにかかっている。\n")
    w("**長さの変わらない改変は検出できない。** 本物のハッシュの代わりにはならない。\n")

    order = [m["run_id"] for m in runs]
    meta = {m["run_id"]: m for m in runs}
    fps = {m["run_id"]: fingerprint(rows, m["run_id"]) for m in runs}

    w("## run ごとの指紋\n")
    w("| run | suite | prompt_set | 条件数 | タスク | 1試行目の入力トークンの幅 |")
    w("|---|---|---|---|---|---|")
    for rid in order:
        m, fp = meta[rid], fps[rid]
        vals = sorted(fp.values())
        rng = "%d〜%d" % (vals[0], vals[-1]) if vals else "-"
        w("| %s | %s | %s | %d | %s | %s |" % (
            rid, m["suite"] or "(名前なし)", m["prompt_set"] or "(記録なし)",
            len(m["conditions"] or []),
            ",".join(sorted({k[1] for k in fp})) or "-", rng))

    w("\n## 指紋が両立する run のまとまり\n")
    w("共通する (条件, タスク) の値がすべて一致する run を繋いだもの。")
    w("同じまとまりなら、同じ入力・同じプロンプトで走ったと考えてよい。")
    w("まとまりが違えば、`suite` の名前が同じでも投入したものが違う。\n")
    for i, ids in enumerate(group_runs(order, fps), 1):
        suites = sorted({meta[r]["suite"] or "(名前なし)" for r in ids})
        prompts = sorted({meta[r]["prompt_set"] or "(記録なし)" for r in ids})
        w("- **群%d** — suite: %s / prompt_set: %s" % (i, ", ".join(suites), ", ".join(prompts)))
        w("  - run: %s" % ", ".join(ids))
        sample = sorted(fps[ids[0]].items())[:3]
        w("  - 例: %s" % "; ".join("%s/%s=%d" % (c, t, v) for (c, t), v in sample))

    w("\n## 同じ (条件, タスク) が run 間で動いたところ\n")
    w("同じ名前の条件・同じ名前のタスクなのに数が違えば、その間に投入したものが変わっている。")
    w("結果JSONの中に、この違いを直接示す記録は無い。\n")
    per_key = defaultdict(dict)
    for rid in order:
        for k, v in fps[rid].items():
            per_key[k][rid] = v
    changed = {k: v for k, v in per_key.items() if len(set(v.values())) > 1}
    if not changed:
        w("変化したものはない。")
    else:
        w("| 条件 | タスク | run ごとの入力トークン |")
        w("|---|---|---|")
        for k in sorted(changed):
            w("| %s | %s | %s |" % (
                k[0], k[1], ", ".join("%s=%d" % (r, t) for r, t in sorted(changed[k].items()))))
        w("")
        w("動いた (条件, タスク) の組: %d / %d" % (len(changed), len(per_key)))

    path = os.path.join(TABLE_DIR, "input_fingerprint.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    print("wrote", path)


if __name__ == "__main__":
    main()
