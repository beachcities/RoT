"""モックだけで全経路を踏み、記録のされ方を検証する。

外部依存なしで走る（pytest も API キーも不要）。

    python selftest.py

ここで確かめているのは「壊れていないこと」であって、自己記述性の効果ではない。
モックの応答はデータ条件を見ないので、この結果から仮説の当否は何も言えない。
"""

import sys
import traceback

import run_benchmark as rb
import summarize
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


def run_repeats(model, condition="raw", repeats=5, max_attempts=3):
    """同じクライアントで反復させる。ランナーの反復ループと同じ形。"""
    client = rb.build_client(mock=True)
    tasks = rb.load_json("tasks/tasks.json")
    data = rb.load_json(
        "data/raw_dataset.json" if condition == "raw" else "data/self_descriptive_dataset.json"
    )
    return [
        rb.run_task(client, model, condition, data, tasks[0], max_attempts, repeat)
        for repeat in range(1, repeats + 1)
    ]


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


@check("reasoning が completion を上回る内訳は取得不能として扱う")
def _():
    r = run("mock-inconsistent-usage")
    assert r["success"] is True
    assert r["reasoning_tokens"] is None, r["reasoning_tokens"]
    assert r["output_tokens"] is None, r["output_tokens"]
    assert r["total_tokens"] == 450, r["total_tokens"]


@check("内訳の総和が合う（出力が負にならない）")
def _():
    for model in SCENARIOS:
        for condition in ("raw", "self_descriptive"):
            r = run(model, condition)
            if r["output_tokens"] is None:
                continue
            assert r["output_tokens"] >= 0, (model, condition, r["output_tokens"])
            assert r["reasoning_tokens"] + r["output_tokens"] == r["completion_tokens"], (
                model, condition, r["reasoning_tokens"], r["output_tokens"], r["completion_tokens"]
            )


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


# --- 反復 ----------------------------------------------------------------


@check("反復: 反復番号が行に残る")
def _():
    rows = run_repeats("mock-reasoning", repeats=3)
    assert [r["repeat"] for r in rows] == [1, 2, 3]


@check("反復: 既定値は5")
def _():
    assert rb.REPEATS == 5, rb.REPEATS


@check("反復: 反復ごとに消費が揺れる経路を踏める")
def _():
    rows = run_repeats("mock-noisy", repeats=5)
    totals = [r["total_tokens"] for r in rows]
    assert len(set(totals)) > 1, totals
    assert all(r["success"] for r in rows)


@check("反復: 5回中3回だけ解ける経路を踏める")
def _():
    rows = run_repeats("mock-flaky", repeats=5)
    assert sum(1 for r in rows if r["success"]) == 3, [r["success"] for r in rows]


# --- 集計 ----------------------------------------------------------------


def fake_row(model, condition, success, total, attempts=1, reasoning=None,
             status="ok", measured=True):
    completion = 100
    return {
        "model": model,
        "condition": condition,
        "task_id": "t",
        "status": status,
        "error": None,
        "success": success,
        "tokens_measured": measured,
        "attempts": attempts,
        "prompt_tokens": total - completion,
        "reasoning_tokens": reasoning,
        "output_tokens": None if reasoning is None else completion - reasoning,
        "completion_tokens": completion,
        "total_tokens": total,
        "rot_per_1k": None,
        "attempt_log": [],
    }


def fake_run(rows):
    return {"conditions": ["raw", "self_descriptive"], "results": rows}


@check("集計: ROT は条件ごとにプールして出す（試行ごとの平均ではない）")
def _():
    rows = [
        fake_row("m", "raw", True, 1000),
        fake_row("m", "raw", False, 3000),
    ]
    stats = summarize.summarize(fake_run(rows))["per_model"]["m"]["per_condition"]["raw"]
    # 正答1件 / 総4000トークン x 1000 = 0.25。試行ごとの平均なら 0.5 になる。
    assert stats["rot_per_1k"] == 0.25, stats["rot_per_1k"]
    assert stats["success_rate"] == 0.5


@check("集計: エラー行と未計測行を除外し、除外数を残す")
def _():
    rows = [
        fake_row("m", "raw", True, 1000),
        fake_row("m", "raw", False, 5000, status="error"),
        fake_row("m", "raw", True, 0, measured=False),
    ]
    summary = summarize.summarize(fake_run(rows))
    stats = summary["per_model"]["m"]["per_condition"]["raw"]
    assert stats["trials"] == 3 and stats["used"] == 1 and stats["excluded"] == 2
    assert stats["total_tokens"] == 1000, stats["total_tokens"]
    assert summary["excluded_trials"] == 2


@check("集計: 内訳が欠けた試行が混ざる条件は CoT を null にする")
def _():
    rows = [
        fake_row("m", "raw", True, 1000, reasoning=40),
        fake_row("m", "raw", True, 1000, reasoning=None),
    ]
    stats = summarize.summarize(fake_run(rows))["per_model"]["m"]["per_condition"]["raw"]
    assert stats["reasoning_tokens"] is None
    assert stats["completion_tokens"] == 200


@check("集計: 条件比は self_descriptive / raw")
def _():
    rows = [
        fake_row("m", "raw", True, 1000, attempts=2),
        fake_row("m", "self_descriptive", True, 500, attempts=1),
    ]
    c = summarize.summarize(fake_run(rows))["per_model"]["m"]["comparison"]
    assert c["available"] is True
    assert c["rot_ratio"] == 2.0, c["rot_ratio"]
    assert c["total_tokens_ratio"] == 0.5, c["total_tokens_ratio"]
    assert c["attempts_ratio"] == 0.5, c["attempts_ratio"]


@check("集計: 基準条件の正答が0なら ROT の比は出さない")
def _():
    rows = [
        fake_row("m", "raw", False, 1000),
        fake_row("m", "self_descriptive", True, 1000),
    ]
    c = summarize.summarize(fake_run(rows))["per_model"]["m"]["comparison"]
    assert c["rot_ratio"] is None
    assert any("定義できない" in n for n in c["notes"])
    assert any("正答率が条件間で異なる" in n for n in c["notes"])


@check("集計: 片側に集計可能な試行が無ければ比を出さない")
def _():
    rows = [
        fake_row("m", "raw", True, 1000),
        fake_row("m", "self_descriptive", True, 0, measured=False),
    ]
    c = summarize.summarize(fake_run(rows))["per_model"]["m"]["comparison"]
    assert c["available"] is False
    assert "self_descriptive" in c["notes"][0]


@check("集計: render が例外なく文字列を返す")
def _():
    rows = [
        fake_row("a", "raw", True, 1000, reasoning=40),
        fake_row("a", "self_descriptive", False, 2000, reasoning=None),
        fake_row("b", "raw", True, 0, measured=False),
        fake_row("b", "self_descriptive", True, 900, status="error"),
    ]
    text = summarize.render(summarize.summarize(fake_run(rows)))
    assert isinstance(text, str) and "条件比" in text
    assert "トークナイザ" in text


# --- ばらつき ------------------------------------------------------------


@check("ばらつき: 中央値・四分位・範囲を出す")
def _():
    d = summarize.distribution([100, 200, 300, 400, 500])
    assert d["n"] == 5
    assert d["median"] == 300, d["median"]
    assert d["min"] == 100 and d["max"] == 500
    assert d["q1"] == 200 and d["q3"] == 400, (d["q1"], d["q3"])


@check("ばらつき: 1点しかなければ四分位は出さない")
def _():
    d = summarize.distribution([100])
    assert d["median"] == 100
    assert d["q1"] is None and d["q3"] is None
    assert summarize.distribution([])["median"] is None


@check("ばらつき: 範囲の重なりを判定する")
def _():
    a = summarize.distribution([100, 200])
    b = summarize.distribution([150, 300])
    c = summarize.distribution([500, 600])
    assert summarize.ranges_overlap(a, b) is True
    assert summarize.ranges_overlap(a, c) is False
    assert summarize.ranges_overlap(a, summarize.distribution([])) is None


@check("ばらつき: プールした ROT と反復ごとの ROT は別物として出す")
def _():
    # 5回中3回だけ 1000 トークンで解け、2回は 3000 トークン使って解けない。
    rows = [fake_row("m", "raw", True, 1000) for _ in range(3)]
    rows += [fake_row("m", "raw", False, 3000) for _ in range(2)]
    st = summarize.summarize(fake_run(rows))["per_model"]["m"]["per_condition"]["raw"]
    assert st["successes"] == 3 and st["used"] == 5
    # プール: 3 / 9000 x 1000 = 0.3333
    assert st["rot_per_1k"] == 0.3333, st["rot_per_1k"]
    # 反復ごと: 0, 0, 1.0, 1.0, 1.0 -> 中央値 1.0。二山になることを示す。
    per_trial = st["rot_per_trial_dist"]
    assert per_trial["median"] == 1.0, per_trial["median"]
    assert per_trial["min"] == 0.0 and per_trial["max"] == 1.0
    assert st["total_tokens_dist"]["min"] == 1000
    assert st["total_tokens_dist"]["max"] == 3000


@check("ばらつき: 範囲が重なるかを条件比の注記に出す")
def _():
    overlapping = [
        fake_row("m", "raw", True, 1000),
        fake_row("m", "raw", True, 2000),
        fake_row("m", "self_descriptive", True, 1500),
        fake_row("m", "self_descriptive", True, 2500),
    ]
    c = summarize.summarize(fake_run(overlapping))["per_model"]["m"]["comparison"]
    assert c["total_tokens_range_overlap"] is True
    assert any("重なっている" in n for n in c["notes"])

    separated = [
        fake_row("m", "raw", True, 1000),
        fake_row("m", "raw", True, 1100),
        fake_row("m", "self_descriptive", True, 5000),
        fake_row("m", "self_descriptive", True, 5100),
    ]
    c = summarize.summarize(fake_run(separated))["per_model"]["m"]["comparison"]
    assert c["total_tokens_range_overlap"] is False
    assert any("重なっていない" in n for n in c["notes"])
    assert c["total_tokens_median_ratio"] == 4.8095, c["total_tokens_median_ratio"]


@check("ばらつき: 反復数とタスク1件の留保を出力に出す")
def _():
    rows = [fake_row("m", "raw", True, 1000), fake_row("m", "self_descriptive", True, 900)]
    run = fake_run(rows)
    run["repeats"] = 5
    summary = summarize.summarize(run)
    assert summary["repeats"] == 5 and summary["tasks"] == ["t"]
    text = summarize.render(summary)
    assert "暫定値" in text
    assert "単一タスクの反復のみ" in text


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
