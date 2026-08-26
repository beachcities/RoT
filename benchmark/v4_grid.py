# -*- coding: utf-8 -*-
"""計器v2の格子を、人が読む形に落とす。

    python v4_grid.py results/run_XXXX.json

出すもの:

* `results/reference/runs/<run_at>_grid.html` — **外部依存なしの一枚**。
  CDN も外部 JS も読まない。単体で開ける静的ファイル。
* 同じ格子のテキスト表（標準出力）。HTML が開けない場所のために、
  ラン記録にも同じものを載せる。

**色は数値の規則だけで付ける。** 指紋三型（散る・割れる・ずれる）のラベルは
付けない——帰属の判断は読む側の仕事で、図に混ぜると判断済みに見えてしまう。

    正解山占有率 > γ            → 緑系
    γ の ±0.05 以内             → 灰
    正解山占有率 < γ            → 赤系
"""

import argparse
import html
import json
import statistics
from pathlib import Path

import summarize_v4

BAND = 0.05          # γ の近傍とみなす幅


def verdict(share, gamma):
    """色の規則。**数値だけで決める。**"""
    if gamma is None:
        return "unknown"
    if abs(share - gamma) <= BAND:
        return "near"
    return "above" if share > gamma else "below"


def collect(run, rel_gap=0.05):
    """セルごとの読み取り量を、格子の座標つきで集める。"""
    spec = {c["name"]: c for c in run.get("condition_spec", [])}
    truth = None
    for t in run.get("inputs", {}).get("tasks", []):
        truth = int(t["ground_truth"])
    rows = {}
    for r in run["results"]:
        r = dict(r, final_number=summarize_v4.final_number(r) if r.get("status") == "ok" else None)
        rows.setdefault(r["condition"], []).append(r)
    cells = {}
    for name, items in rows.items():
        meta = spec.get(name, {})
        d = summarize_v4.describe(items, truth, meta.get("gamma"))
        toks = [x.get("total_tokens") or 0 for x in items]
        d["トークン中央値"] = statistics.median(toks) if toks else 0
        d["t"] = meta.get("t")
        d["d"] = meta.get("d")
        d["arm"] = meta.get("arm")
        d["条件"] = name
        d["判定"] = verdict(d["正解山の占有率"], meta.get("gamma"))
        d["回答"] = sorted(
            ((v, sum(1 for x in items if x["final_number"] == v))
             for v in {x["final_number"] for x in items if x["final_number"] is not None}),
            key=lambda p: -p[1])
        d["正解値"] = truth
        cells[name] = d
    return cells


def cell_at(cells, t, d):
    """格子の (t, d) に置くセル。**既定の腕（振る）を優先する。**

    同じ座標に振る側と固定側が両方あるとき、どちらを表に出すかを暗黙に
    決めてしまわないための明示。
    """
    here = [c for c in cells.values() if c["t"] == t and c["d"] == d]
    if not here:
        return None
    varied = [c for c in here if c.get("arm") == "varied"]
    return (varied or here)[0]


def text_grid(cells):
    """テキストの格子。**HTML が開けない場所のために同じものを出す。**"""
    ts = sorted({c["t"] for c in cells.values() if c["t"] is not None})
    ds = sorted({c["d"] for c in cells.values() if c["d"] is not None})
    mark = {"above": ">", "near": "=", "below": "<", "unknown": "?"}
    lines = []
    head = "      " + "".join(f"  d={d:<14d}" for d in ds)
    lines.append(head)
    for t in ts:
        row = f"t={t}  "
        for d in ds:
            cell = cell_at(cells, t, d)
            if cell is None:
                row += "  " + "-" * 14
                continue
            row += (f"  {cell['正解山の占有率']:.2f}{mark[cell['判定']]}"
                    f"{cell['gamma']:.2f} 山{cell['山の数']:<2d}0×{cell['0回答数']:<2d}")
        lines.append(row)
    lines.append("")
    lines.append("  各セル: 正解山占有率 [>|=|<] γ  山の数  0回答数")
    lines.append("  記号は数値の規則のみ（> は γ 超え、= は ±0.05 以内、< は γ 未満）。")
    return "\n".join(lines)


CSS = """
:root { --above:#1b7f4b; --above-bg:#e6f4ec; --near:#5b6470; --near-bg:#eef0f2;
        --below:#a8322b; --below-bg:#fbeceb; --ink:#1a1c1e; --line:#d6d9dd; }
* { box-sizing: border-box; }
body { margin:0; padding:32px; background:#fff; color:var(--ink);
       font-family: "Helvetica Neue", Arial, "Hiragino Sans", "Yu Gothic", sans-serif;
       line-height:1.6; }
h1 { font-size:20px; margin:0 0 4px; }
h2 { font-size:15px; margin:32px 0 10px; border-bottom:1px solid var(--line);
     padding-bottom:6px; }
.meta { color:#5b6470; font-size:13px; margin-bottom:24px; }
.meta code { background:#f4f5f7; padding:1px 5px; border-radius:3px; }
table { border-collapse:collapse; }
.grid td, .grid th { border:1px solid var(--line); padding:0; text-align:center; }
.grid th { background:#f4f5f7; font-size:12px; font-weight:600; padding:6px 10px;
           color:#5b6470; }
.cell { display:block; padding:10px 8px; min-width:118px; }
.cell .big { font-size:19px; font-weight:700; letter-spacing:-0.02em; }
.cell .sub { font-size:11px; color:#5b6470; margin-top:3px; }
.above .cell { background:var(--above-bg); } .above .big { color:var(--above); }
.near  .cell { background:var(--near-bg);  } .near  .big { color:var(--near); }
.below .cell { background:var(--below-bg); } .below .big { color:var(--below); }
.answers { font-size:13px; }
.answers table { width:100%; max-width:560px; margin:4px 0 18px; }
.answers td { border-bottom:1px solid var(--line); padding:3px 8px; }
.answers .n { text-align:right; color:#5b6470; width:60px; }
.answers .correct { font-weight:700; color:var(--above); }
.legend { font-size:13px; background:#f9fafb; border:1px solid var(--line);
          border-radius:6px; padding:14px 18px; max-width:760px; }
.legend dt { font-weight:600; margin-top:8px; }
.legend dd { margin:0 0 0 16px; color:#3d444d; }
.swatch { display:inline-block; width:11px; height:11px; border-radius:2px;
          vertical-align:middle; margin-right:5px; }
"""


def render_html(run, cells):
    esc = html.escape
    ts = sorted({c["t"] for c in cells.values() if c["t"] is not None})
    ds = sorted({c["d"] for c in cells.values() if c["d"] is not None})
    out = [f"<!doctype html><html lang='ja'><head><meta charset='utf-8'>",
           f"<title>計器v2 格子 {esc(run['run_at'])}</title>",
           f"<style>{CSS}</style></head><body>"]
    out.append(f"<h1>計器v2 分布プローブ — 格子</h1>")
    out.append(
        "<p class='meta'>"
        f"ラン <code>{esc(run['run_at'])}</code> ／ "
        f"モデル <code>{esc(', '.join(run['models']))}</code> ／ "
        f"thinking {esc(str(run.get('thinking_mode')))} ／ "
        f"試行上限 {run['max_attempts']}（1 は一発勝負） ／ "
        f"標本 n={run['repeats']} ／ "
        f"inputs 指紋 <code>{esc(run['fingerprint']['inputs'])}</code>"
        "</p>")

    out.append("<table class='grid'><tr><th></th>")
    for d in ds:
        out.append(f"<th>d={d}</th>")
    out.append("</tr>")
    for t in ts:
        out.append(f"<tr><th>t={t}</th>")
        for d in ds:
            cell = cell_at(cells, t, d)
            if cell is None:
                out.append("<td><span class='cell'>—</span></td>")
                continue
            out.append(
                f"<td class='{cell['判定']}'><span class='cell'>"
                f"<span class='big'>{cell['正解山の占有率']:.2f} / {cell['gamma']:.2f}</span>"
                f"<span class='sub'>山 {cell['山の数']}　0回答 {cell['0回答数']}<br>"
                f"token中央 {cell['トークン中央値']:,.0f}</span>"
                "</span></td>")
        out.append("</tr>")
    out.append("</table>")

    out.append("<h2>セルごとの回答</h2><div class='answers'>")
    for name in sorted(cells, key=lambda k: (cells[k]["t"], cells[k]["d"])):
        c = cells[name]
        out.append(f"<p><strong>t={c['t']} d={c['d']}</strong>"
                   f"（{esc(name)}、γ={c['gamma']:.3f}、正解 {c['正解値']}）</p><table>")
        for value, n in c["回答"]:
            klass = " class='correct'" if value == c["正解値"] else ""
            mark = " ← 正解" if value == c["正解値"] else ""
            out.append(f"<tr><td{klass}>{value}{mark}</td>"
                       f"<td class='n'>× {n}</td></tr>")
        if not c["回答"]:
            out.append("<tr><td>（数値が取れた標本なし）</td><td class='n'></td></tr>")
        out.append("</table>")
    out.append("</div>")

    out.append("""<h2>凡例</h2><div class='legend'><dl>
<dt>正解山占有率</dt><dd>n 標本のうち、正解値を含む山に入った割合。</dd>
<dt>γ（偶然水準）</dt><dd>そのセルで、残る不明コードから当て推量したときに
当たる確率。<code>1/C(6−t−d, 2−t)</code> で計算する（t=2 は 1）。
測った占有率をこれと突き合わせる。</dd>
<dt>山の数</dt><dd>回答を数直線に並べ、値の広がりに対して 5% より広い隙間で
切った数。山の数は先に決めていない。</dd>
<dt>0回答</dt><dd>「対応がデータに無いので該当は0」と述べて 0 を答えた標本の数。
誤答とは性質が違うので数え分けている。山推定にはそのまま入っている。</dd>
<dt>token中央値</dt><dd>そのセルの1標本あたり総トークンの中央値。</dd>
<dt>色</dt><dd>
<span class='swatch' style='background:var(--above)'></span>正解山占有率 &gt; γ ／
<span class='swatch' style='background:var(--near)'></span>γ の ±0.05 以内 ／
<span class='swatch' style='background:var(--below)'></span>正解山占有率 &lt; γ。
<strong>色は数値の規則だけで付けている。</strong>壊れ方の型のラベルは付けない——
どの型に当たるかの帰属は読む側の仕事で、図に混ぜると判断済みに見えてしまうから。</dd>
</dl>
<p><strong>n=10 はパイロット水準であり、検定はしていない。</strong>
占有率と γ を並べて置いてあるだけで、差が偶然でないとは主張していない。</p>
</div>""")
    out.append("</body></html>")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description="計器v2の格子を人が読む形に落とす")
    ap.add_argument("path")
    ap.add_argument("--out-dir", default="results/reference/runs")
    args = ap.parse_args()
    run = json.load(open(args.path, encoding="utf-8"))
    cells = collect(run)
    print(text_grid(cells))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{run['run_at']}_grid.html"
    target.write_text(render_html(run, cells), encoding="utf-8")
    print(f"\n書き出した: {target}")


if __name__ == "__main__":
    main()
