"""ROT benchmark: measure token cost per outcome across data conditions.

Runs each task under two data conditions (raw / self-descriptive) for each
model, retrying on failure up to MAX_ATTEMPTS. Tokens from failed attempts are
included in the denominator: the size of the search is itself the weight of the
context that was missing from the data.

See README.md for what this does and does not measure.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

import summarize

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

# .env はこのファイルの隣を見る。リポジトリ直下から起動されても拾えるように。
load_dotenv(BASE_DIR / ".env")


def env_int(name, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        raise SystemExit(f"環境変数 {name} は整数である必要があります: {raw!r}")


BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("API_KEY") or "dummy"
MODELS = [m.strip() for m in os.getenv("BENCHMARK_MODELS", "gpt-4o-mini").split(",") if m.strip()]
MAX_ATTEMPTS = env_int("MAX_ATTEMPTS", 3)
# 1セル（モデル×条件×タスク）を何回繰り返すか。条件間に差が出たとき、それが
# ばらつきの範囲かを言うために要る。5 は暫定値であって確定した設計ではない。
# README の「反復回数について」を参照。
REPEATS = env_int("REPEATS", 5)
REQUEST_TIMEOUT = env_int("REQUEST_TIMEOUT", 120)
MAX_RETRIES = env_int("MAX_RETRIES", 2)

PROMPT_TEMPLATE = """以下のデータを参照して、質問に回答してください。

### 提供データ
{data}

### 質問
{query}

数値のみを、単位や記号を付けずに出力してください。"""

RETRY_TEMPLATE = """その回答は正しくありません。データを読み直して、もう一度回答してください。

数値のみを、単位や記号を付けずに出力してください。"""

# 本文が空で返ったとき、履歴に空文字を積むと拒否するサーバがあるための代替。
EMPTY_ANSWER_PLACEHOLDER = "(応答なし)"

# 反復ごとの明細をそのまま並べると読めなくなるので、この件数を超えたら省略する。
TRIAL_TABLE_LIMIT = 30


def build_client(mock=False):
    """Return the API client. --mock swaps in a stand-in that never uses HTTP."""
    if mock:
        from mock_client import MockClient

        return MockClient()
    from openai import OpenAI

    return OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT,
        max_retries=MAX_RETRIES,
    )


def load_json(relative_path):
    with open(BASE_DIR / relative_path, encoding="utf-8") as f:
        return json.load(f)


def extract_number(text):
    """回答から採点対象の数値を取り出す。

    採点規則（結果に効くので明示しておく）:
      1. NFKC で正規化する（全角数字を半角に落とす）
      2. 桁区切り・空白・通貨記号を除去する
      3. 残った整数の並びのうち最後のものを答えとみなす

    最初のものを採ると、「該当は1社です。売上は1200000000円です」の 1 を拾って
    誤答扱いになる。誤答扱いはリトライを誘発して分母を膨らませるため、測ろうと
    している量そのものを歪める。最後を採る規則にも「1200000000円（1200百万円）」
    のような後置注記を拾い損ねる弱点があるので、抽出結果は attempt_log に
    extracted として残し、後から採点をやり直せるようにする。
    """
    if not text:
        return None
    normalized = unicodedata.normalize("NFKC", text)
    stripped = re.sub(r"[,\s円¥￥]", "", normalized)
    matches = re.findall(r"\d+", stripped)
    if not matches:
        return None
    return matches[-1].lstrip("0") or "0"


def normalize_truth(value):
    """正答側も同じ規則で正規化して突き合わせる。"""
    return extract_number(str(value))


def token_breakdown(usage):
    """usage から内訳を取り出す。

    戻り値は dict。usage を返さないサーバがあるため、取れたかどうかを measured
    で区別する。取れていないことを 0 と書くと、解けた試行が ROT=0（最悪）として
    記録されてしまう。
    """
    if usage is None:
        return {"measured": False, "prompt": 0, "completion": 0, "reasoning": None, "total": 0}

    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        details = usage.get("completion_tokens_details")
    else:
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        details = getattr(usage, "completion_tokens_details", None)

    prompt_tokens = prompt_tokens or 0
    completion_tokens = completion_tokens or 0
    total_tokens = total_tokens or (prompt_tokens + completion_tokens)

    reasoning = None
    if details is not None:
        value = getattr(details, "reasoning_tokens", None)
        if value is None and isinstance(details, dict):
            value = details.get("reasoning_tokens")
        if value is not None:
            reasoning = value

    # completion は reasoning を含む。上回っていたら内訳が壊れているので、
    # 差を出力トークンとして記録せず、取得できなかったものとして扱う。
    if reasoning is not None and reasoning > completion_tokens:
        reasoning = None

    return {
        "measured": total_tokens > 0,
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "reasoning": reasoning,
        "total": total_tokens,
    }


def run_task(client, model, condition, data, task, max_attempts=None, repeat=1):
    """1タスクを1条件で1回走らせる。正答するか試行を使い切るまで繰り返す。

    ここでいう「試行（attempt）」は同じ会話の中でのリトライ。反復（repeat）は
    会話を捨てて最初からやり直す独立な標本で、呼び出し側が回す。
    """
    max_attempts = MAX_ATTEMPTS if max_attempts is None else max_attempts
    messages = [
        {
            "role": "user",
            "content": PROMPT_TEMPLATE.format(
                data=json.dumps(data, ensure_ascii=False, indent=2),
                query=task["query"],
            ),
        }
    ]
    truth = normalize_truth(task["ground_truth"])

    attempts = []
    totals = {"prompt": 0, "completion": 0, "reasoning": 0, "total": 0}
    reasoning_available = True
    tokens_measured = True
    success = False
    answer = None
    status = "ok"
    error = None
    started = time.time()

    for attempt_no in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(model=model, messages=messages)
        except Exception as exc:  # 何が飛んでも、そこまでに消費したトークンは残す
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            attempts.append({"attempt": attempt_no, "error": error})
            break

        answer = (response.choices[0].message.content or "").strip()
        usage = token_breakdown(getattr(response, "usage", None))

        if not usage["measured"]:
            tokens_measured = False
        if usage["reasoning"] is None:
            reasoning_available = False
        else:
            totals["reasoning"] += usage["reasoning"]
        totals["prompt"] += usage["prompt"]
        totals["completion"] += usage["completion"]
        totals["total"] += usage["total"]

        extracted = extract_number(answer)
        success = extracted is not None and extracted == truth
        attempts.append(
            {
                "attempt": attempt_no,
                "answer": answer,
                "extracted": extracted,
                "success": success,
                "tokens_measured": usage["measured"],
                "prompt_tokens": usage["prompt"],
                "reasoning_tokens": usage["reasoning"],
                "completion_tokens": usage["completion"],
                "total_tokens": usage["total"],
            }
        )

        if success:
            break

        messages.append({"role": "assistant", "content": answer or EMPTY_ANSWER_PLACEHOLDER})
        messages.append({"role": "user", "content": RETRY_TEMPLATE})

    elapsed = time.time() - started

    # 内訳が全試行で揃っているときだけ output を出す。揃っていないものを足すと、
    # 隠れたCoTが出力トークンに紛れて内訳の総和が合わなくなる。
    reasoning_total = totals["reasoning"] if reasoning_available else None
    output_total = totals["completion"] - totals["reasoning"] if reasoning_available else None

    # 計測できていない試行、途中で落ちた試行は ROT を算出しない。0.0 と書くと
    # 「解けたのに効率が最悪だった」と読めてしまう。
    if status == "error" or not tokens_measured or totals["total"] <= 0:
        rot = None
    else:
        rot = round((1.0 if success else 0.0) / totals["total"] * 1000, 4)

    return {
        "model": model,
        "condition": condition,
        "task_id": task["task_id"],
        "repeat": repeat,
        "status": status,
        "error": error,
        "success": success,
        "tokens_measured": tokens_measured,
        "final_answer": answer,
        "attempts": len(attempts),
        "prompt_tokens": totals["prompt"],
        "reasoning_tokens": reasoning_total,
        "output_tokens": output_total,
        "completion_tokens": totals["completion"],
        "total_tokens": totals["total"],
        "rot_per_1k": rot,
        "latency_sec": round(elapsed, 2),
        "attempt_log": attempts,
    }


def format_cell(value):
    return "n/a" if value is None else str(value)


def trial_state(result):
    if result["status"] == "error":
        return "ERROR"
    if not result["tokens_measured"]:
        return "no-usage"
    return "ok" if result["success"] else "wrong"


def print_trial_table(results):
    cols = [("model", 24), ("condition", 18), ("task", 10), ("rep", 5),
            ("state", 9), ("try", 5), ("CoT", 8), ("total", 8), ("ROT/1k", 9)]
    header = "".join(f"{name:<{width}}" for name, width in cols)
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['model']:<24}{r['condition']:<18}{r['task_id']:<10}"
            f"{r.get('repeat', 1):<5}{trial_state(r):<9}{r['attempts']:<5}"
            f"{format_cell(r['reasoning_tokens']):<8}{r['total_tokens']:<8}"
            f"{format_cell(r['rot_per_1k']):<9}"
        )


def parse_args():
    parser = argparse.ArgumentParser(description="ROT benchmark runner")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="ダミー応答で全経路を通す（HTTPを叩かない。APIキー不要）",
    )
    parser.add_argument("--models", help="カンマ区切りのモデル名（BENCHMARK_MODELS を上書き）")
    parser.add_argument("--max-attempts", type=int, help="1タスクあたりの最大試行回数を上書き")
    parser.add_argument("--repeats", type=int, help="1セルあたりの反復回数を上書き（REPEATS）")
    parser.add_argument(
        "--show-trials",
        action="store_true",
        help="反復1回ごとの明細を表示する（既定は件数が多いと省略。JSONには常に入る）",
    )
    parser.add_argument("--no-save", action="store_true", help="results/ に書き出さない")
    return parser.parse_args()


def configure_stdout():
    """cp932 コンソールで表外の文字に当たっても、書き出しまで落とさない。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    configure_stdout()
    args = parse_args()

    models = MODELS
    if args.models:
        models = [m.strip() for m in args.models.split(",") if m.strip()]
    elif args.mock:
        from mock_client import DEFAULT_MOCK_MODELS

        models = DEFAULT_MOCK_MODELS

    max_attempts = args.max_attempts or MAX_ATTEMPTS
    repeats = args.repeats or REPEATS
    if repeats < 1:
        raise SystemExit("--repeats / REPEATS は1以上である必要があります")
    client = build_client(mock=args.mock)

    tasks = load_json("tasks/tasks.json")
    conditions = {
        "raw": load_json("data/raw_dataset.json"),
        "self_descriptive": load_json("data/self_descriptive_dataset.json"),
    }

    cells = len(models) * len(conditions) * len(tasks)
    print(f"{cells} セル x 反復 {repeats} 回 = {cells * repeats} 回の実行")

    results = []
    for model in models:
        for condition, data in conditions.items():
            for task in tasks:
                for repeat in range(1, repeats + 1):
                    print(
                        f"running: {model} / {condition} / {task['task_id']}"
                        f" [{repeat}/{repeats}]"
                    )
                    result = run_task(
                        client, model, condition, data, task, max_attempts, repeat
                    )
                    if result["status"] == "error":
                        print(f"  error: {result['error']}")
                    elif not result["tokens_measured"]:
                        print("  warning: usage が返らないためトークンを計測できていません")
                    results.append(result)

    print()
    if args.show_trials or len(results) <= TRIAL_TABLE_LIMIT:
        print_trial_table(results)
    else:
        print(
            f"反復ごとの明細 {len(results)} 件は省略した（--show-trials で表示）。"
            "JSONには常に入っている。"
        )

    run = {
        "run_at": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "base_url": "mock://" if args.mock else BASE_URL,
        "mock": args.mock,
        "models": models,
        "max_attempts": max_attempts,
        "repeats": repeats,
        "conditions": list(conditions),
        "tasks": [t["task_id"] for t in tasks],
        "results": results,
    }

    run["summary"] = summarize.summarize(run)
    print()
    if args.mock:
        print("※ --mock 実行。以下はダミー応答に対する集計であり、実測ではありません。")
    print(summarize.render(run["summary"]))

    if not args.no_save:
        RESULTS_DIR.mkdir(exist_ok=True)
        out_path = RESULTS_DIR / f"run_{run['run_at']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
        print(f"\nsaved: {out_path}")

    return run


if __name__ == "__main__":
    main()
