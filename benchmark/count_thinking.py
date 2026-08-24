# -*- coding: utf-8 -*-
"""思考テキストのトークン数を、そのモデルのトークナイザで数えて結果に書き足す。

    python count_thinking.py results/reference/run_....json
    python count_thinking.py <file> --dry-run
    python count_thinking.py <file> --tokenizer allenai/Olmo-3-7B-Think

中間推論について、これまで取れていたのは文字数だけだった。文字数はトークン数の
代わりにならない（言語や記号の混ざり方で比が変わる）。サーバが `usage` で
`reasoning_tokens` を返さない場合に、取り出したテキストを数える。

## 何を正とするか

* **サーバが返した値があれば、それが正。** `thinking_tokens_source` は `server`。
* 返らない場合だけ、ここで数える。`thinking_tokens_source` は `tokenizer`。
* **両方取れた場合は上書きせず、差を `thinking_tokens_delta` に残す。**
  差の大きさが分かれば、近似の妥当性を後から評価できる。
* 数えられない場合は `null` のままにする。**文字数からの換算はしない。**

## 近似であることについて

ここで数えるのは「取り出したテキストを、いま符号化し直したときの長さ」であって、
**生成時に実際に流れたトークン列とは一致しない可能性がある**。

* 開始タグ・終了タグそのものは思考テキストに含まれていない（切り出しで落としている）
* 特殊トークンの扱いはテンプレート依存で、ここでは付けずに数えている
* 前後の空白の削り方が、切り出しの時点と生成時とで違いうる

したがって `tokenizer` 由来の値は**下限寄りの近似**である。

## 近似の確かめ方

`reasoning_tokens` が返らないサーバでも、**`completion_tokens` は返る**。生成された
本文は「思考 + タグ + 最終回答」なので、

    残差 = completion_tokens - (数えた思考 + 数えた最終回答)

が、切り出しで落としたぶん（タグと前後の空白）にあたる。この残差が小さく安定していれば、
数え方が生成時の符号化とほぼ一致していることになる。`--verify` で出す。

実測（Olmo-3-7B-Think、76試行）: 残差は 0〜8 トークン、中央値 4、
`completion_tokens` に対して 0.06%（最大 0.72%）。`</think>` と前後の改行ぶんに相当し、
**近似は下限寄りで、ずれは1試行あたり数トークン**であることが確かめられた。

## トークナイザの取り方

`tokenizer.json`（fast tokenizer）を Hugging Face から取ってきて `tokenizers` で読む。
`transformers` は入れない（torch を引き込むため）。取得は初回だけで、以後は
ローカルのキャッシュを見る。
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# API 経由のモデルは Hugging Face にトークナイザが無い。そもそも思考テキストも
# 返らないので数える対象が無く、素通りする。
NO_TOKENIZER = ("gpt-", "o1", "o3", "o4", "claude-", "gemini-", "mock-")


def load_tokenizer(model_id):
    """model_id のトークナイザを返す。取れなければ (None, 理由)。"""
    if any(model_id.startswith(prefix) for prefix in NO_TOKENIZER):
        return None, f"{model_id} は公開トークナイザを持たない系統"
    try:
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
    except ImportError:
        return None, "tokenizers / huggingface_hub が入っていない（pip install tokenizers huggingface_hub）"
    # TLS を中継する環境では、Python 同梱の証明書では検証が通らないことがある
    # （実測: この環境がそうだった）。OS の証明書ストアを使う。
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    try:
        path = hf_hub_download(repo_id=model_id, filename="tokenizer.json")
    except Exception as exc:  # 404、ネットワーク不通、認証など
        return None, f"tokenizer.json を取得できない: {type(exc).__name__}: {exc}"
    return Tokenizer.from_file(path), None


def count(tokenizer, text):
    """特殊トークンを付けずに数える。生成時の列とは一致しない近似。"""
    return len(tokenizer.encode(text, add_special_tokens=False).ids)


def residuals(run, tokenizer):
    """completion_tokens と、数え直した「思考 + 最終回答」との残差。

    サーバが reasoning_tokens を返さなくても completion_tokens は返るので、
    これを相手に数え方の妥当性を確かめられる。
    """
    out = []
    for result in run["results"]:
        for attempt in result.get("attempt_log", []):
            if "answer" not in attempt or not attempt.get("thinking"):
                continue
            completion = attempt.get("completion_tokens")
            if not completion:
                continue
            counted = (count(tokenizer, attempt["thinking"])
                       + count(tokenizer, attempt["answer"] or ""))
            out.append({"completion_tokens": completion, "counted": counted,
                        "residual": completion - counted})
    return out


def annotate(run, tokenizer, model_id):
    """試行ごとに thinking_tokens を埋める。返り値は集計用の内訳。"""
    stats = {"server": 0, "tokenizer": 0, "none": 0, "both": 0, "deltas": []}
    for result in run["results"]:
        per_trial = []
        for attempt in result.get("attempt_log", []):
            if "answer" not in attempt:          # 通信が落ちた試行
                continue
            server = attempt.get("reasoning_tokens")
            text = attempt.get("thinking")
            counted = None
            if tokenizer is not None and text:
                counted = count(tokenizer, text)

            if server is not None:
                attempt["thinking_tokens"] = server
                attempt["thinking_tokens_source"] = "server"
                stats["server"] += 1
                if counted is not None:
                    # 上書きしない。差だけ残す。
                    attempt["thinking_tokens_counted"] = counted
                    attempt["thinking_tokens_delta"] = counted - server
                    stats["both"] += 1
                    stats["deltas"].append(counted - server)
            elif counted is not None:
                attempt["thinking_tokens"] = counted
                attempt["thinking_tokens_source"] = "tokenizer"
                stats["tokenizer"] += 1
            else:
                attempt["thinking_tokens"] = None
                attempt["thinking_tokens_source"] = None
                stats["none"] += 1
            if attempt.get("thinking_tokens") is not None:
                per_trial.append(attempt["thinking_tokens"])

        result["thinking_tokens"] = sum(per_trial) if per_trial else None
        result["thinking_tokens_source"] = next(
            (a.get("thinking_tokens_source") for a in result.get("attempt_log", [])
             if a.get("thinking_tokens_source")), None)
    run["thinking_token_count"] = {
        "tokenizer": model_id if tokenizer is not None else None,
        "note": ("サーバが返した値を正とし、返らない分だけトークナイザで数えた。"
                 "数えた値は生成時のトークン列とは一致しない近似。"),
    }
    return stats


def main():
    parser = argparse.ArgumentParser(description="思考テキストのトークン数を数えて書き足す")
    parser.add_argument("path", help="結果JSON")
    parser.add_argument("--tokenizer", help="トークナイザのモデルID（既定は結果のモデル名）")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに内訳だけ出す")
    parser.add_argument("--verify", action="store_true",
                        help="completion_tokens との残差を出して、数え方の妥当性を確かめる")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    path = Path(args.path)
    with open(path, encoding="utf-8") as f:
        run = json.load(f)

    model_id = args.tokenizer or (run.get("models") or [""])[0]
    tokenizer, why = load_tokenizer(model_id)
    print(f"source: {path.name}")
    print(f"モデル: {model_id}")
    if tokenizer is None:
        print(f"トークナイザ: 使わない（{why}）")
    else:
        print(f"トークナイザ: {model_id} の tokenizer.json")

    stats = annotate(run, tokenizer, model_id)
    print()
    print(f"  サーバが返した試行        {stats['server']:>4} 件")
    print(f"  トークナイザで数えた試行  {stats['tokenizer']:>4} 件")
    print(f"  数えられなかった試行      {stats['none']:>4} 件（null のまま）")
    if stats["both"]:
        deltas = stats["deltas"]
        print(f"  両方取れた試行            {stats['both']:>4} 件 / "
              f"差（数えた値 - サーバ値）: 最小 {min(deltas)} 中央 "
              f"{sorted(deltas)[len(deltas) // 2]} 最大 {max(deltas)}")

    totals = [r["thinking_tokens"] for r in run["results"] if r.get("thinking_tokens")]
    if totals:
        print(f"\n  試行あたりの思考トークン: 件数 {len(totals)} / "
              f"最小 {min(totals):,} / 最大 {max(totals):,} / 合計 {sum(totals):,}")

    if args.verify and tokenizer is not None:
        import statistics

        rows = residuals(run, tokenizer)
        if rows:
            res = [r['residual'] for r in rows]
            rel = [r['residual'] / r['completion_tokens'] * 100 for r in rows]
            print()
            print(f"  近似の確かめ（completion_tokens - 数えた「思考+最終回答」）: {len(rows)} 試行")
            print(f"    残差 中央 {statistics.median(res):.0f} / 最小 {min(res)} / 最大 {max(res)} トークン")
            print(f"    completion_tokens に対する割合 中央 {statistics.median(rel):.2f}% / 最大 {max(rel):.2f}%")
            print("    残差は切り出しで落としたタグと前後の空白にあたる。"
                  "小さく安定していれば、数え方は生成時とほぼ一致している。")
        else:
            print()
            print("  近似の確かめ: 対象の試行が無い（思考テキストが要る）")

    if args.dry_run:
        print("\n(--dry-run のため書き込んでいない)")
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump(run, f, ensure_ascii=False, indent=2)
    print(f"\n書き足した: {path}")


if __name__ == "__main__":
    main()
