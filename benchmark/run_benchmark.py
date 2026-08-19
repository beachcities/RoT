"""ROT benchmark: measure token cost per outcome across data conditions.

Runs each task under two data conditions (raw / self-descriptive) for each
model, retrying on failure up to MAX_ATTEMPTS. Tokens from failed attempts are
included in the denominator: the size of the search is itself the weight of the
context that was missing from the data.

See README.md for what this does and does not measure.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"

BASE_URL = os.getenv("BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("API_KEY") or "dummy"
MODELS = [m.strip() for m in os.getenv("BENCHMARK_MODELS", "gpt-4o-mini").split(",") if m.strip()]
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "3"))

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

PROMPT_TEMPLATE = """以下のデータを参照して、質問に回答してください。

### 提供データ
{data}

### 質問
{query}

数値のみを、単位や記号を付けずに出力してください。"""

RETRY_TEMPLATE = """その回答は正しくありません。データを読み直して、もう一度回答してください。

数値のみを、単位や記号を付けずに出力してください。"""


def load_json(relative_path):
    with open(BASE_DIR / relative_path, encoding="utf-8") as f:
        return json.load(f)


def extract_number(text):
    """Pull the first bare integer out of a model reply."""
    digits = re.sub(r"[,\s円]", "", text or "")
    match = re.search(r"\d+", digits)
    return match.group(0) if match else None


def token_breakdown(usage):
    """Return (prompt, reasoning, output, total). reasoning is None if unavailable."""
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)

    reasoning = None
    details = getattr(usage, "completion_tokens_details", None)
    if details is not None:
        value = getattr(details, "reasoning_tokens", None)
        if value is None and isinstance(details, dict):
            value = details.get("reasoning_tokens")
        if value is not None:
            reasoning = value

    output_tokens = completion_tokens - reasoning if reasoning is not None else completion_tokens
    return prompt_tokens, reasoning, output_tokens, total_tokens


def run_task(model, condition, data, task):
    """Run one task under one condition, retrying until correct or exhausted."""
    messages = [
        {
            "role": "user",
            "content": PROMPT_TEMPLATE.format(
                data=json.dumps(data, ensure_ascii=False, indent=2),
                query=task["query"],
            ),
        }
    ]

    attempts = []
    totals = {"prompt": 0, "reasoning": 0, "output": 0, "total": 0}
    reasoning_available = True
    success = False
    answer = None
    started = time.time()

    for attempt_no in range(1, MAX_ATTEMPTS + 1):
        response = client.chat.completions.create(model=model, messages=messages)
        answer = (response.choices[0].message.content or "").strip()
        prompt_t, reasoning_t, output_t, total_t = token_breakdown(response.usage)

        if reasoning_t is None:
            reasoning_available = False
        else:
            totals["reasoning"] += reasoning_t
        totals["prompt"] += prompt_t
        totals["output"] += output_t
        totals["total"] += total_t

        success = extract_number(answer) == task["ground_truth"]
        attempts.append(
            {
                "attempt": attempt_no,
                "answer": answer,
                "success": success,
                "prompt_tokens": prompt_t,
                "reasoning_tokens": reasoning_t,
                "output_tokens": output_t,
                "total_tokens": total_t,
            }
        )

        if success:
            break

        messages.append({"role": "assistant", "content": answer})
        messages.append({"role": "user", "content": RETRY_TEMPLATE})

    elapsed = time.time() - started
    rot = (1.0 if success else 0.0) / totals["total"] * 1000 if totals["total"] else 0.0

    return {
        "model": model,
        "condition": condition,
        "task_id": task["task_id"],
        "success": success,
        "final_answer": answer,
        "attempts": len(attempts),
        "prompt_tokens": totals["prompt"],
        "reasoning_tokens": totals["reasoning"] if reasoning_available else None,
        "output_tokens": totals["output"],
        "total_tokens": totals["total"],
        "rot_per_1k": round(rot, 4),
        "latency_sec": round(elapsed, 2),
        "attempt_log": attempts,
    }


def format_cell(value):
    return "n/a" if value is None else str(value)


def main():
    tasks = load_json("tasks/tasks.json")
    conditions = {
        "raw": load_json("data/raw_dataset.json"),
        "self_descriptive": load_json("data/self_descriptive_dataset.json"),
    }

    results = []
    for model in MODELS:
        for condition, data in conditions.items():
            for task in tasks:
                print(f"running: {model} / {condition} / {task['task_id']}")
                try:
                    results.append(run_task(model, condition, data, task))
                except Exception as exc:
                    print(f"  failed: {exc}")
                    results.append(
                        {
                            "model": model,
                            "condition": condition,
                            "task_id": task["task_id"],
                            "error": str(exc),
                        }
                    )

    print()
    header = f"{'model':<28}{'condition':<20}{'task':<10}{'ok':<5}{'try':<5}{'CoT':<9}{'total':<9}{'ROT/1k':<9}"
    print(header)
    print("-" * len(header))
    for r in results:
        if "error" in r:
            print(f"{r['model']:<28}{r['condition']:<20}{r['task_id']:<10}error")
            continue
        print(
            f"{r['model']:<28}{r['condition']:<20}{r['task_id']:<10}"
            f"{str(r['success']):<5}{r['attempts']:<5}"
            f"{format_cell(r['reasoning_tokens']):<9}{r['total_tokens']:<9}{r['rot_per_1k']:<9}"
        )

    print(
        "\nNote: total_tokens is tokenizer-dependent. Compare conditions within a "
        "model, not absolute values across models."
    )

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"run_{stamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_at": stamp,
                "base_url": BASE_URL,
                "models": MODELS,
                "max_attempts": MAX_ATTEMPTS,
                "results": results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\nsaved: {out_path}")


if __name__ == "__main__":
    main()
