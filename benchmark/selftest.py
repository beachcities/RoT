"""モックだけで全経路を踏み、記録のされ方を検証する。

外部依存なしで走る（pytest も API キーも不要）。

    python selftest.py

ここで確かめているのは「壊れていないこと」であって、自己記述性の効果ではない。
モックの応答はデータ条件を見ないので、この結果から仮説の当否は何も言えない。
"""

import sys
import traceback

import run_benchmark as rb
from mock_client import SCENARIOS

CHECKS = []


def check(name):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn

    return decorator


def run(model, condition="raw", max_attempts=3):
    """モックで1セル走らせて結果行を返す。"""
    client = rb.build_client(mock=True)
    tasks = rb.load_json("tasks/tasks.json")
    data = rb.load_json(
        "data/raw_dataset.json" if condition == "raw" else "data/self_descriptive_dataset.json"
    )
    return rb.run_task(client, model, condition, data, tasks[0], max_attempts)


# --- 採点規則 ------------------------------------------------------------


@check("extract_number: 素の数値")
def _():
    assert rb.extract_number("1200000000") == "1200000000"


@check("extract_number: 桁区切りと通貨記号を落とす")
def _():
    assert rb.extract_number("1,200,000,000円") == "1200000000"


@check("extract_number: 全角数字を半角に正規化する")
def _():
    assert rb.extract_number("１２００００００００") == "1200000000"


@check("extract_number: 文章中では最後の数値を採る")
def _():
    assert rb.extract_number("該当は1社です。売上は1200000000円です。") == "1200000000"


@check("extract_number: 数値が無ければ None")
def _():
    assert rb.extract_number("わかりません") is None
    assert rb.extract_number("") is None
    assert rb.extract_number(None) is None


# --- トークンの記録 ------------------------------------------------------


@check("reasoning_tokens を返すモデルは数値で記録される")
def _():
    r = run("mock-reasoning")
    assert r["reasoning_tokens"] == 200, r["reasoning_tokens"]
    assert r["output_tokens"] == 60, r["output_tokens"]
    assert r["status"] == "ok" and r["success"] is True


@check("reasoning_tokens を返さないモデルは落ちずに null になる")
def _():
    r = run("mock-no-reasoning")
    assert r["status"] == "ok", r["status"]
    assert r["success"] is True
    assert r["reasoning_tokens"] is None, r["reasoning_tokens"]
    assert r["output_tokens"] is None, r["output_tokens"]
    assert r["completion_tokens"] > 0
    assert r["total_tokens"] > 0
    assert r["rot_per_1k"] is not None


@check("reasoning_tokens=0 は null ではなく 0 として記録される")
def _():
    r = run("mock-reasoning-zero")
    assert r["reasoning_tokens"] == 0, r["reasoning_tokens"]
    assert r["output_tokens"] == 60, r["output_tokens"]


@check("completion_tokens_details が dict のサーバでも読める")
def _():
    r = run("mock-dict-usage")
    assert r["reasoning_tokens"] == 200, r["reasoning_tokens"]


@check("試行ごとに内訳の有無が違う場合、内訳は null にする")
def _():
    r = run("mock-mixed-reasoning")
    assert r["success"] is True
    assert r["reasoning_tokens"] is None
    assert r["output_tokens"] is None
    assert r["completion_tokens"] == 320, r["completion_tokens"]
    assert r["total_tokens"] == 1240, r["total_tokens"]


@check("usage を返さないサーバでは ROT を算出しない")
def _():
    r = run("mock-no-usage")
    assert r["success"] is True
    assert r["tokens_measured"] is False
    assert r["rot_per_1k"] is None, r["rot_per_1k"]


# --- リトライと分母 ------------------------------------------------------


@check("失敗した試行のトークンが分母に積まれる")
def _():
    r = run("mock-retry")
    assert r["attempts"] == 3, r["attempts"]
    assert r["success"] is True
    per_attempt = sum(a["total_tokens"] for a in r["attempt_log"])
    assert r["total_tokens"] == per_attempt, (r["total_tokens"], per_attempt)
    # 3回目だけなら 540。捨てられた探索が入っていることを確かめる。
    assert r["total_tokens"] > r["attempt_log"][-1]["total_tokens"]


@check("試行を使い切って解けなければ success=False, ROT=0")
def _():
    r = run("mock-always-wrong")
    assert r["attempts"] == 3
    assert r["success"] is False
    assert r["rot_per_1k"] == 0.0, r["rot_per_1k"]


@check("--max-attempts が効く")
def _():
    r = run("mock-always-wrong", max_attempts=1)
    assert r["attempts"] == 1, r["attempts"]


@check("本文が空で返っても次の試行に進める")
def _():
    r = run("mock-empty")
    assert r["attempts"] == 2
    assert r["success"] is True
    assert r["attempt_log"][0]["extracted"] is None


# --- 通信の失敗 ----------------------------------------------------------


@check("1回目から落ちても例外を外に出さない")
def _():
    r = run("mock-error")
    assert r["status"] == "error", r["status"]
    assert r["error"] and "MockAPIError" in r["error"]
    assert r["rot_per_1k"] is None


@check("途中で落ちても、そこまでのトークンは失われない")
def _():
    r = run("mock-error-midway")
    assert r["status"] == "error"
    assert r["attempts"] == 2
    assert r["total_tokens"] == 680, r["total_tokens"]
    assert r["rot_per_1k"] is None


# --- 全シナリオの網羅 ----------------------------------------------------


@check("全シナリオが両条件で例外なく完走する")
def _():
    for model in SCENARIOS:
        for condition in ("raw", "self_descriptive"):
            r = run(model, condition)
            assert r["status"] in ("ok", "error"), (model, condition, r["status"])
            assert r["model"] == model and r["condition"] == condition
            assert isinstance(r["attempt_log"], list) and r["attempt_log"]


def main():
    rb.configure_stdout()
    failed = 0
    for name, fn in CHECKS:
        try:
            fn()
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
        else:
            print(f"ok    {name}")
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
