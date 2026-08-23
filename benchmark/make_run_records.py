# -*- coding: utf-8 -*-
"""ランごとの記録を1ラン1ファイルで書き出す。

    python make_run_records.py            # 公開対象のランすべて
    python make_run_records.py <file>     # 1本だけ

**結果JSONから機械的に作る。** 手で書いた記録は次のランで途切れるので、
書き足す運用にはしない。記録していなかった項目は空欄にして、その旨を書く。
推測で埋めない。

## 読み方の留保をどこに置いたか

全ランに共通する留保（分子が二値であること、総トークンがトークナイザ依存であること等）は
**共通の1ファイル `READING.md` に置き、各ランから参照する**。ラン固有の留保
（反復数・タスク数・除外件数から決まるもの）だけを各ランのファイルに書く。

そうしたのは、共通部分を各ランに書き写すと、**測り方を直したときに古いランの記録と
新しいランの記録が食い違う**ため。留保は測り方の性質であって、そのランの性質ではない。
分割は `summarize.STATIC_CAVEATS` と `summarize.run_caveats()` に対応している。
"""

import argparse
import json
import sys
from pathlib import Path

import summarize

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
REFERENCE_DIR = RESULTS_DIR / "reference"
RUNS_DIR = REFERENCE_DIR / "runs"

NOT_RECORDED = "（記録していない）"


def value(x):
    """空・None を「記録していない」に潰す。推測で埋めない。"""
    if x is None or x == "" or x == {}:
        return NOT_RECORDED
    return x


def server_location(route, run):
    if route.get("local_server") is True:
        return "同じ機械の中（ローカル）"
    url = route.get("base_url") or run.get("base_url") or ""
    if not url:
        return NOT_RECORDED
    if "localhost" in url or "127.0.0.1" in url:
        return "同じ機械の中（ローカル）"
    if url.startswith("mock://"):
        return "モック（HTTPなし）"
    return "外部のAPI"


def route_lines(run):
    """実行経路。RUN_ROUTE を記録するようになる前のランは空欄になる。"""
    route = run.get("route") or {}
    env = run.get("environment") or {}
    rows = [
        ("覚え書き（`RUN_ROUTE`）", value(route.get("note"))),
        ("エンドポイント", value(route.get("base_url") or run.get("base_url"))),
        # base_url は古いランにも入っているので、そこから導ける分は導く（推測ではない）
        ("サーバの所在", server_location(route, run)),
        ("プラットフォーム", value(env.get("platform"))),
        ("Python", value(env.get("python"))),
        ("OpenAI SDK", value(env.get("openai_sdk"))),
        ("コマンド", "`" + " ".join(run["argv"]) + "`" if run.get("argv") else NOT_RECORDED),
    ]
    return rows


def provenance_lines(run):
    fp = run.get("fingerprint") or {}
    settings = fp.get("settings") or {}
    sampling = settings.get("sampling_requested") or {}
    duration = run.get("duration_sec")
    rows = [
        ("実行日時（UTC）", value(run.get("started_at") or run.get("run_at"))),
        ("所要", f"{duration:,.0f} 秒（{duration / 60:.0f} 分）" if duration else NOT_RECORDED),
        ("モデル", ", ".join(run.get("models") or []) or NOT_RECORDED),
        ("応答したモデルの実体名", ", ".join(sorted({
            r.get("response_model") for r in run["results"] if r.get("response_model")
        })) or NOT_RECORDED),
        ("組（suite）", value(run.get("suite"))),
        ("プロンプト", value(run.get("prompt_set"))),
        ("反復", value(run.get("repeats"))),
        ("試行上限", value(run.get("max_attempts"))),
        ("生成上限（`max_tokens`）", value(sampling.get("max_tokens"))),
        ("サンプリング", ", ".join(f"{k}={v}" for k, v in sampling.items()) or NOT_RECORDED),
        ("実行数", f"{len(run['results'])}（うち集計から除外 "
                   f"{sum(1 for r in run['results'] if r['status'] != 'ok')}）"),
        ("途中経過から引き継いだ試行", value(run.get("resumed_trials"))),
    ]
    return rows


def fingerprint_lines(run):
    fp = run.get("fingerprint") or {}
    if not fp:
        return [("指紋", NOT_RECORDED + "（`inputs` を保存していない世代の結果）")]
    git = fp.get("git") or {}
    return [
        ("入力（`inputs`）", f"`{fp.get('inputs')}`"),
        ("タスク", f"`{fp.get('tasks')}`"),
        ("プロンプト", f"`{fp.get('prompt')}`"),
        ("サンプリング", f"`{fp.get('sampling')}`"),
        ("コミット", f"`{git.get('commit')}`" if git.get("commit") else NOT_RECORDED),
        ("`benchmark/` に未コミットの変更", {True: "あり", False: "なし"}.get(
            git.get("dirty"), NOT_RECORDED)),
    ]


def table(rows):
    out = ["| 項目 | 値 |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in rows]
    return out


def render_record(run, ledger_note=""):
    # 保存されている summary は当時の集計コードのもので、列が足りないことがある。
    # 常に現在のコードで作り直す。何が表示されたかを再現するのではなく、
    # いま同じ結果を集計するとこうなる、という形で残す。
    summary = summarize.summarize(run)
    lines = [f"# ラン記録 {run.get('run_at')}", ""]
    if ledger_note:
        lines += [f"> 台帳の注記: {ledger_note}", ""]
    lines += ["## 実行の素性", ""] + table(provenance_lines(run)) + [""]
    lines += ["## 実行経路", ""] + table(route_lines(run)) + [""]
    if any(v == NOT_RECORDED for _, v in route_lines(run)):
        lines += ["空欄は、そのランの時点で記録していなかった項目。"
                  "推測で埋めていない。以後は `RUN_ROUTE` に書けば残る。", ""]
    lines += ["## 指紋", ""] + table(fingerprint_lines(run)) + [""]
    lines += ["## 集計の出力", "",
              "結果JSONから **現在の `summarize.py` で作り直したもの**。"
              "実行時に標準出力へ流れたものを捕捉していないため、当時の表示そのものではない"
              "（集計コードが変わっていれば列が増減する）。", "", "```"]
    lines += summarize.render(summary).split("\n")
    lines += ["```", ""]
    lines += ["## 試行の一覧", "", "```"]
    lines += trial_table(run)
    lines += ["```", ""]
    lines += ["## 読み方の留保", "",
              "全ランに共通する留保は [READING.md](../READING.md) にある。"
              "以下はこのランに固有のもの。", ""]
    run_only = summarize.run_caveats(summary)
    lines += (["```"] + run_only + ["```"]) if run_only else ["（なし）"]
    return "\n".join(lines) + "\n"


def trial_table(run):
    """試行の一覧。集計と同じ並びで、思考字数を足したもの。"""
    cols = [("model", 26), ("condition", 18), ("task", 10), ("rep", 5), ("state", 9),
            ("try", 5), ("total", 9), ("think", 10), ("ROT/1k", 9)]
    header = "".join(f"{n:<{w}}" for n, w in cols)
    out = [header, "-" * len(header)]
    for r in run["results"]:
        state = "ERROR" if r["status"] == "error" else (
            "ok" if r["success"] else ("no-usage" if not r["tokens_measured"] else "wrong"))
        out.append(
            f"{r['model']:<26}{r['condition']:<18}{r['task_id']:<10}{r.get('repeat', 1):<5}"
            f"{state:<9}{r['attempts']:<5}{r['total_tokens']:<9}"
            f"{(r.get('thinking_chars') if r.get('thinking_chars') is not None else 'n/a'):<10}"
            f"{r['rot_per_1k'] if r['rot_per_1k'] is not None else 'n/a':<9}"
        )
    return out


def render_reading():
    lines = ["# 読み方の留保（全ランに共通）", "",
             "各ランの記録から参照している。**測り方の性質であって、個々のランの性質ではない。**",
             "ランごとに変わる留保（反復数・タスク数・除外件数から決まるもの）は、",
             "各ランの記録の末尾にある。", "",
             "この一覧は `summarize.STATIC_CAVEATS` から生成しており、集計の出力に",
             "毎回印字されるものと同一である。", "", "```"]
    lines += summarize.STATIC_CAVEATS
    lines += ["```", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="ランごとの記録を書き出す")
    parser.add_argument("path", nargs="?", help="結果JSON（省略時は公開対象すべて）")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    import export_reference

    if args.path:
        paths = [Path(args.path)]
    else:
        paths = [REFERENCE_DIR / n for n in export_reference.REFERENCE]

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (REFERENCE_DIR / "READING.md").write_text(render_reading(), encoding="utf-8")
    print(f"書き出した: {(REFERENCE_DIR / 'READING.md').relative_to(BASE_DIR)}")

    for path in paths:
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        note = export_reference.NOTES.get(path.name, "")
        out = RUNS_DIR / f"{run['run_at']}.md"
        out.write_text(render_record(run, note), encoding="utf-8")
        print(f"書き出した: {out.relative_to(BASE_DIR)} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
