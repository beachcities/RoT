"""モックだけで全経路を踏み、記録のされ方を検証する。

外部依存なしで走る（pytest も API キーも不要）。

    python selftest.py

ここで確かめているのは「壊れていないこと」であって、自己記述性の効果ではない。
モックの応答はデータ条件を見ないので、この結果から仮説の当否は何も言えない。
"""

import json
import pathlib
import tempfile
import os
import sys
import traceback

from types import SimpleNamespace

import run_benchmark as rb
import summarize
from mock_client import SCENARIOS

CHECKS = []


def check(name):
    def decorator(fn):
        CHECKS.append((name, fn))
        return fn

    return decorator


SUITE = rb.SUITE


def load(condition=None, suite=None):
    """条件を1つ取り出す。組によって条件名が違うので、無ければ先頭を使う。

    ここでの検査は記録のされ方についてのもので、どの条件かは問わない。
    """
    tasks, conditions, _ = rb.load_suite(suite or SUITE)
    if condition not in conditions:
        condition = next(iter(conditions))
    return tasks, conditions[condition], condition


def run(model, condition=None, max_attempts=3, suite=None):
    """モックで1セル走らせて結果行を返す。"""
    client = rb.build_client(mock=True)
    tasks, data, condition = load(condition, suite)
    return rb.run_task(client, model, condition, data, tasks[0], max_attempts)


def run_repeats(model, condition=None, repeats=5, max_attempts=3, suite=None):
    """同じクライアントで反復させる。ランナーの反復ループと同じ形。"""
    client = rb.build_client(mock=True)
    tasks, data, condition = load(condition, suite)
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


@check("extract_number: 改行で隔てた数値が繋がらない")
def _():
    # 実測で見つけた欠陥。空白をまとめて消すと別々の数値が1つになる。
    assert rb.extract_number("1,860,000,000\n\n1860000000") == "1860000000"
    assert rb.extract_number("1860 x 1,000,000 = 1,860,000,000\n\n1860000000") == "1860000000"
    assert rb.extract_number("55\n55") == "55"


@check("extract_number: 空でない最後の行を優先する")
def _():
    # プロンプトが「最後の行には数値のみ」と指示しているので、そこを先に見る。
    assert rb.extract_number("計算過程で 999 を使った\n\n1200\n\n") == "1200"
    # 最後の行に数値が無ければ本文全体から採る
    assert rb.extract_number("答えは 1200 です\nよろしくお願いします") == "1200"


@check("採点し直し: 入力を保存していない結果は採点し直せない")
def _():
    import regrade

    assert regrade.regrade({"results": [], "inputs": {}}) is None
    run_ = {
        "inputs": {"tasks": [{"task_id": "t", "ground_truth": "55"}]},
        "results": [{
            "model": "m", "condition": "c", "task_id": "t", "repeat": 1,
            "attempt_log": [{"attempt": 1, "answer": "55\n55", "extracted": "5555",
                             "success": False}],
        }],
    }
    changed = regrade.regrade(run_)
    assert len(changed) == 1, changed
    assert changed[0]["now_extracted"] == "55" and changed[0]["now_success"] is True


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


@check("全シナリオが最下位と最上位の条件で例外なく完走する")
def _():
    conditions = list(rb.load_suite(SUITE)[1])
    for model in SCENARIOS:
        for condition in (conditions[0], conditions[-1]):
            r = run(model, condition)
            assert r["status"] in ("ok", "error"), (model, condition, r["status"])
            assert r["model"] == model and r["condition"] == condition
            assert isinstance(r["attempt_log"], list) and r["attempt_log"]


# --- プロンプト ------------------------------------------------------------


def prompt_names():
    with open(rb.PROMPTS_PATH, encoding="utf-8") as f:
        return [k for k in json.load(f) if not k.startswith("_")]


@check("プロンプト: 全種類が読めて差し込み位置を持つ")
def _():
    names = prompt_names()
    assert len(names) >= 2, names
    for name in names:
        p = rb.load_prompts(name)
        assert "{data}" in p["prompt"] and "{query}" in p["prompt"], name
        assert p["retry"].strip(), name


@check("プロンプト: 存在しない名前を指定したら止まる")
def _():
    try:
        rb.load_prompts("no_such_prompt")
    except SystemExit as exc:
        assert "見つかりません" in str(exc), exc
    else:
        raise AssertionError("存在しないプロンプトが受理された")


@check("プロンプト: 両条件にまったく同じ文面を投げている")
def _():
    tasks, conditions, _ = rb.load_suite(SUITE)
    task = tasks[0]
    for name in prompt_names():
        prompts = rb.load_prompts(name)
        sent = []
        for condition, data in conditions.items():
            client = rb.build_client(mock=True)
            rb.run_task(client, "mock-reasoning", condition, data, task, 1, 1, prompts)
            sent.append(client.first_messages[0])
        expected = [
            prompts["prompt"].format(
                data=json.dumps(data, ensure_ascii=False, indent=2), query=task["query"]
            )
            for data in conditions.values()
        ]
        # データ本体以外は一字一句同じであること
        assert sent == expected, name


@check("プロンプト: 投げた全文が結果に残る")
def _():
    import contextlib
    import io

    for name in prompt_names():
        with contextlib.redirect_stdout(io.StringIO()):
            run = run_main("--prompt", name, "--models", "mock-reasoning", "--repeats", "1")
        assert run["prompt_set"] == name, run["prompt_set"]
        assert run["prompt_text"] == {
            "prompt": rb.load_prompts(name)["prompt"],
            "retry": rb.load_prompts(name)["retry"],
        }, name


# --- 記録項目 --------------------------------------------------------------


@check("記録: 応答の実体名・system_fingerprint・finish_reason が残る")
def _():
    r = run("mock-reasoning")
    assert r["response_model"] == "mock-model-2026-01-01", r["response_model"]
    assert r["system_fingerprint"] == "fp_mock0000", r["system_fingerprint"]
    assert r["finish_reason"] == "stop", r["finish_reason"]
    for a in r["attempt_log"]:
        assert a["response_model"] and a["system_fingerprint"] and a["finish_reason"]


@check("思考: <think> を本文から切り出してテキストごと残す")
def _():
    r = run("mock-think-inline", max_attempts=1)
    a = r["attempt_log"][0]
    assert a["thinking"] and "社名から推す" in a["thinking"], a["thinking"]
    # 本文からは <think> が取り除かれ、採点は最終回答だけを見る
    assert "<think>" not in a["answer"], a["answer"]
    assert a["success"] is True, a["answer"]
    assert a["thinking_chars"] == len(a["thinking"])
    assert r["thinking_chars"] == a["thinking_chars"]


@check("思考: reasoning_content で分けて返る場合も拾う")
def _():
    r = run("mock-think-field", max_attempts=1)
    a = r["attempt_log"][0]
    assert a["thinking"] and "税額との比" in a["thinking"], a["thinking"]
    assert a["answer"] == a["answer"].strip() and "<think>" not in a["answer"]
    assert r["thinking_chars"] == len(a["thinking"])


@check("思考: 返さないモデルでは null のまま（0 と区別する）")
def _():
    r = run("mock-reasoning", max_attempts=1)
    assert r["thinking_chars"] is None, r["thinking_chars"]
    assert r["attempt_log"][0]["thinking"] is None


@check("思考: 複数の <think> があれば連結する")
def _():
    text = "<think>一つ目</think>途中<think>二つ目</think>\n55"
    thinking, answer, source = rb.split_thinking(SimpleNamespace(content=text))
    assert source == "tag_pair", source
    assert thinking == "一つ目" + chr(10) + "二つ目", thinking
    assert answer.endswith("55") and "<think>" not in answer, answer


@check("記録: finish_reason が stop 以外でもそのまま残る")
def _():
    r = run("mock-length-stop", max_attempts=2)
    assert r["finish_reason"] == "length", r["finish_reason"]


@check("生成上限: 到達を記録し、集計から外さない")
def _():
    r = run("mock-length-stop", max_attempts=2)
    assert r["output_capped_attempts"] == 2, r["output_capped_attempts"]
    assert all(a["output_capped"] for a in r["attempt_log"])
    # 到達しても status は ok のまま。除外の条件に触らない。
    assert r["status"] == "ok" and r["tokens_measured"]
    rows = [dict(r, model="m", condition="c", task_id="t", repeat=1)]
    st = summarize.summarize({"results": rows, "conditions": ["c"], "max_attempts": 2,
                              "repeats": 1})["per_model"]["m"]["per_condition"]["c"]
    assert st["used"] == 1, st["used"]          # 除外されていない
    assert st["output_capped"] == 1, st["output_capped"]


@check("生成上限: 上限を送らない設定では 0 のまま")
def _():
    r = run("mock-reasoning", max_attempts=1)
    assert r["output_capped_attempts"] == 0, r["output_capped_attempts"]
    assert "max_tokens" not in rb.sampling_params() or rb.MAX_OUTPUT_TOKENS > 0


@check("記録: 受け付けられないサンプリング設定は落として理由を残す")
def _():
    sampling = {"requested": rb.sampling_params(), "used": rb.sampling_params(), "dropped": {}}
    tasks, data, condition = load()
    client = rb.build_client(mock=True)
    r = rb.run_task(client, "mock-no-temperature", condition, data, tasks[0], 1, 1, None, sampling)
    assert r["status"] == "ok", r["error"]
    assert set(sampling["dropped"]) == {"temperature", "seed"}, sampling["dropped"]
    assert set(sampling["used"]) == {"top_p"}, sampling["used"]
    assert sampling["requested"] == rb.sampling_params()  # 要求した内容は変えない


@check("記録: ラン全体に argv・SDK版・開始終了時刻・サンプリングが残る")
def _():
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        run_ = run_main("--models", "mock-reasoning", "--repeats", "1")
    for key in ("argv", "environment", "started_at", "finished_at", "duration_sec", "sampling"):
        assert key in run_, key
    assert run_["environment"]["python"] and run_["environment"]["openai_sdk"]
    assert run_["sampling"]["mock-reasoning"]["requested"] == rb.sampling_params()
    assert run_["fingerprint"]["settings"]["sampling_requested"] == rb.sampling_params()


# --- 思考のオン/オフ -------------------------------------------------------


def with_thinking(mode, fn):
    """THINKING を一時的に差し替えて実行する。"""
    saved = rb.THINKING
    rb.THINKING = mode
    try:
        return fn()
    finally:
        rb.THINKING = saved


@check("thinking: off にすると chat_template_kwargs で切られる")
def _():
    on = with_thinking("on", lambda: run("mock-thinking-toggle", max_attempts=1))
    off = with_thinking("off", lambda: run("mock-thinking-toggle", max_attempts=1))
    assert on["thinking_chars"], on["thinking_chars"]
    assert off["thinking_chars"] is None, off["thinking_chars"]
    # 切ったほうが生成トークンが少ない
    assert off["completion_tokens"] < on["completion_tokens"], (
        off["completion_tokens"], on["completion_tokens"])


@check("thinking: 送る中身は on で空、off で enable_thinking=False")
def _():
    assert with_thinking("on", rb.thinking_body) == {}
    assert with_thinking("off", rb.thinking_body) == {
        "chat_template_kwargs": {"enable_thinking": False}}


@check("thinking: 結果と指紋に on/off が残り、指紋が別になる")
def _():
    import contextlib
    import io

    argv = ["--mock", "--models", "mock-thinking-toggle", "--suite", "v3_levels",
            "--conditions", "l6_codes_doc", "--tasks", "task_06", "--repeats", "1",
            "--no-save"]

    def once():
        saved = sys.argv
        sys.argv = ["run_benchmark.py", *argv]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                return rb.main()
        finally:
            sys.argv = saved

    on = with_thinking("on", once)
    off = with_thinking("off", once)
    assert on["thinking_mode"] == "on" and off["thinking_mode"] == "off"
    assert on["fingerprint"]["thinking_mode"] == "on"
    assert off["fingerprint"]["settings"]["thinking_mode"] == "off"
    # 指紋が別なら、途中経過の置き場所も別になる（混ざらない）
    assert rb.partial_path(on["fingerprint"]) != rb.partial_path(off["fingerprint"])


@check("thinking: off を受け付けないサーバなら止まる（黙って続けない）")
def _():
    class _Refusing:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("unknown field enable_thinking")

    sampling = {"requested": {}, "used": {}, "dropped": {}}
    try:
        with_thinking("off", lambda: rb.create_completion(
            _Refusing(), "m", [{"role": "user", "content": "x"}], sampling))
    except SystemExit as exc:
        assert "成立しない" in str(exc), exc
    else:
        raise AssertionError("受け付けられなくても続行してしまった")


# --- 思考のトークン数 ------------------------------------------------------


class _StubTokenizer:
    """空白区切りで数えるだけの替え玉。検査で通信しないため。"""

    class _Enc:
        def __init__(self, ids):
            self.ids = ids

    def encode(self, text, add_special_tokens=False):
        return self._Enc(text.split())


@check("思考: 三通りの経路をすべて拾い、どれで取れたかを残す")
def _():
    cases = {
        "mock-think-field": "reasoning_content",   # サーバが分けて返す
        "mock-think-inline": "tag_pair",           # 対で本文に現れる
        "mock-think-close": "closing_tag",         # 終了タグだけ
        "mock-think-alt-tag": "tag_pair",          # 別系統のタグ
    }
    for model, expected in cases.items():
        r = run(model, max_attempts=1)
        assert r["thinking_source"] == expected, (model, r["thinking_source"])
        a = r["attempt_log"][0]
        assert a["thinking"], model
        assert "</think>" not in a["answer"] and "</reasoning>" not in a["answer"], model
        assert a["success"] is True, (model, a["answer"])


@check("思考: 返さないモデルでは経路も null")
def _():
    r = run("mock-reasoning", max_attempts=1)
    assert r["thinking_source"] is None, r["thinking_source"]


@check("トークン数: サーバが返さない分だけ数え、由来を残す")
def _():
    import count_thinking as ct

    run_ = {"models": ["stub"], "results": [{
        "attempt_log": [
            {"attempt": 1, "answer": "x", "thinking": "a b c", "reasoning_tokens": None},
        ]}]}
    stats = ct.annotate(run_, _StubTokenizer(), "stub")
    a = run_["results"][0]["attempt_log"][0]
    assert a["thinking_tokens"] == 3, a
    assert a["thinking_tokens_source"] == "tokenizer", a
    assert stats["tokenizer"] == 1 and stats["server"] == 0


@check("トークン数: サーバの値を正とし、上書きせずに差を残す")
def _():
    import count_thinking as ct

    run_ = {"models": ["stub"], "results": [{
        "attempt_log": [
            {"attempt": 1, "answer": "x", "thinking": "a b c d", "reasoning_tokens": 6},
        ]}]}
    ct.annotate(run_, _StubTokenizer(), "stub")
    a = run_["results"][0]["attempt_log"][0]
    assert a["thinking_tokens"] == 6, a            # サーバ値のまま
    assert a["thinking_tokens_source"] == "server"
    assert a["thinking_tokens_counted"] == 4       # 数えた値は別に残す
    assert a["thinking_tokens_delta"] == -2


@check("トークン数: 数えられなければ null。文字数から換算しない")
def _():
    import count_thinking as ct

    run_ = {"models": ["stub"], "results": [{
        "attempt_log": [
            {"attempt": 1, "answer": "x", "thinking": None, "reasoning_tokens": None},
        ]}]}
    ct.annotate(run_, None, "stub")               # トークナイザ無し
    a = run_["results"][0]["attempt_log"][0]
    assert a["thinking_tokens"] is None, a
    assert a["thinking_tokens_source"] is None, a
    assert run_["results"][0]["thinking_tokens"] is None


@check("トークン数: 公開トークナイザを持たない系統は理由つきで素通りする")
def _():
    import count_thinking as ct

    tok, why = ct.load_tokenizer("gpt-4o-mini")
    assert tok is None and "トークナイザ" in why, why


# --- 要求仕様の逆算 --------------------------------------------------------


@check("逆算: 問いを主語にした文は落とす（課題の曖昧さであってデータの欠落ではない）")
def _():
    import derive_requirements as dr

    keep = "The problem is, the data doesn't list the industry type for each company."
    drop = "The question doesn't specify whether to include closed companies in the total."
    assert dr.extract(keep) == [keep], dr.extract(keep)
    assert dr.extract(drop) == [], dr.extract(drop)


@check("逆算: 中身の話は落とす（記述の欠落だけを採る）")
def _():
    import derive_requirements as dr

    # 「その業種の企業が入っていない」はデータの中身についての観察で、要求仕様にならない
    drop = "Unfortunately the dataset doesn't have any companies in the academic research sector."
    assert dr.extract(drop) == [], dr.extract(drop)
    keep = "But the dataset doesn't have explicit labels for these industries anywhere."
    assert dr.extract(keep) == [keep], dr.extract(keep)


@check("逆算: 束ねは先勝ちではなく一致数で決める")
def _():
    import derive_requirements as dr

    # 「外部」の語が1つ入っているだけで external_reference に持っていかれてはいけない。
    # 実測でこの誤分類が起きていた。
    s = ("Since I can't access external data, the mapping of industry codes to "
         "industry names and what each code means is still missing.")
    assert dr.bucket(s) == "industry_code_meaning", dr.bucket(s)
    # 素直に外部参照を指す文はそちらに入る
    t = "The schema at code_list_reference is not included, so the definitions are unavailable."
    assert dr.bucket(t) == "external_reference", dr.bucket(t)


@check("逆算: 見出しと根拠の文が同じ束から出ている")
def _():
    import derive_requirements as dr

    sentences = [
        "The problem is, the data doesn't list the industry type for each company.",
        "The schema at code_list_reference is not included, so the definitions are unavailable.",
    ]
    for s in sentences:
        name = dr.bucket(s)
        assert name is not None, s
        # 束の正規表現が、その文に実際に当たっていること
        pattern = next(p for k, p, _ in dr.BUCKETS if k == name)
        assert pattern.search(s), (name, s)


@check("逆算: 抽出器は 4 の確認でも同じものが使われる")
def _():
    import derive_requirements as dr
    import inspect

    src = inspect.getsource(dr.verify)
    assert "extract(" in src, "確認の段が別の数え方をしている"


# --- 途中経過と再開 --------------------------------------------------------


class _Boom(RuntimeError):
    """途中で落ちる状況を作るための例外。"""


def run_until_crash(argv, after):
    """after 件だけ書けたところで落とす。落ちなければ AssertionError。"""
    import contextlib
    import io

    real = rb.run_task
    seen = {"n": 0}

    def crashing(*a, **k):
        seen["n"] += 1
        if seen["n"] > after:
            raise _Boom("模擬的な異常終了")
        return real(*a, **k)

    rb.run_task = crashing
    saved = sys.argv
    sys.argv = ["run_benchmark.py", *argv]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rb.main()
    except _Boom:
        return
    finally:
        rb.run_task = real
        sys.argv = saved
    raise AssertionError("落ちなかった")


RESUME_ARGV = ["--mock", "--models", "mock-reasoning", "--suite", "v3_levels",
               "--tasks", "task_04,task_06",
               "--conditions", "l0_opaque,l1_names,l2_units_ref", "--repeats", "1"]


@check("再開: 途中で落ちてもそこまでが残り、続きから回せる")
def _():
    import contextlib
    import io

    for f in rb.PARTIAL_DIR.glob("partial_*.jsonl"):
        f.unlink()
    run_until_crash(RESUME_ARGV, after=3)
    partials = sorted(rb.PARTIAL_DIR.glob("partial_*.jsonl"))
    assert len(partials) == 1, partials
    lines = partials[0].read_text(encoding="utf-8").strip().split(chr(10))
    assert len(lines) - 1 == 3, len(lines)      # 先頭は見出し

    saved = sys.argv
    sys.argv = ["run_benchmark.py", *RESUME_ARGV]
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run = rb.main()
    finally:
        sys.argv = saved
    assert len(run["results"]) == 6, len(run["results"])
    assert run["resumed_trials"] == 3, run["resumed_trials"]
    assert buf.getvalue().count("running:") == 3   # 残りだけ回した
    keys = {(r["model"], r["condition"], r["task_id"], r["repeat"]) for r in run["results"]}
    assert len(keys) == 6, keys
    assert not partials[0].exists(), "完走したのに途中経過が残っている"


@check("再開: 指紋が違う途中経過は受け付けない")
def _():
    try:
        rb.load_partial(_fake_partial({"prompt": "ちがう"}), {"prompt": "本物"})
    except SystemExit as exc:
        assert "一致しません" in str(exc), exc
    else:
        raise AssertionError("指紋が違うのに受理された")


def _fake_partial(header):
    path = rb.PARTIAL_DIR / "partial_test.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"header": header}, ensure_ascii=False) + chr(10),
                    encoding="utf-8")
    return path


@check("再開: 壊れた行は捨てて読み進める")
def _():
    path = _fake_partial({"a": 1})
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"model": "m", "condition": "c", "task_id": "t", "repeat": 1},
                           ensure_ascii=False) + chr(10))
        f.write("{壊れた行" + chr(10))
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        done = rb.load_partial(path, {"a": 1})
    assert len(done) == 1, done
    path.unlink()


@check("再開: --no-save では途中経過を書かない")
def _():
    import contextlib
    import io

    for f in rb.PARTIAL_DIR.glob("partial_*.jsonl"):
        f.unlink()
    saved = sys.argv
    sys.argv = ["run_benchmark.py", *RESUME_ARGV, "--no-save"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rb.main()
    finally:
        sys.argv = saved
    assert not list(rb.PARTIAL_DIR.glob("partial_*.jsonl"))


@check("再開: 途中経過の置き場所は設定の指紋で決まる")
def _():
    a = rb.partial_path({"prompt": "x"})
    b = rb.partial_path({"prompt": "y"})
    assert a != b, (a, b)
    assert a == rb.partial_path({"prompt": "x"})


# --- 結果の同定 ------------------------------------------------------------


@check("指紋: 実行結果に入力の指紋と本文が残る")
def _():
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        run = run_main("--suite", "v3_levels", "--models", "mock-reasoning", "--repeats", "1")
    fp = run["fingerprint"]
    for key in ("suite", "tasks", "condition_spec", "conditions", "inputs",
                "prompt_set", "prompt", "code", "git", "settings"):
        assert key in fp, key
    tasks, conditions, spec = rb.load_suite("v3_levels")
    assert fp["tasks"] == rb.digest(tasks)
    assert fp["conditions"] == {n: rb.digest(d) for n, d in conditions.items()}
    # 本文そのものも入っている。組は編集されるので、名前だけでは同定できない。
    assert run["inputs"]["tasks"] == tasks
    assert list(run["inputs"]["conditions"]) == list(conditions)


@check("指紋: 中身が違えば指紋も違う")
def _():
    _, conditions, _ = rb.load_suite("v3_levels")
    digests = {c: rb.digest(d) for c, d in conditions.items()}
    assert len(set(digests.values())) == len(digests), digests
    # 並び順が変われば別の入力として扱う（項目順は水準の定義そのもの）
    assert rb.digest({"a": 1, "b": 2}) != rb.digest({"b": 2, "a": 1})
    # 整形の違いでは変わらない
    assert rb.digest(json.loads('{"a":1}')) == rb.digest(json.loads('{ "a" : 1 }'))


@check("指紋: 後付けは復元できないものを復元不能と書く")
def _():
    import backfill_fingerprints as bf

    assert bf.backfill({"fingerprint": {}}) is None
    block = bf.backfill({"suite": "v3_levels", "conditions": ["a"], "models": ["m"]})
    assert "conditions_data" in block["unrecoverable"]
    assert "tasks" in block["unrecoverable"]
    assert "prompt" in block["unrecoverable"]
    assert "prompt" not in block["recoverable"]
    withtext = bf.backfill({"prompt_text": {"prompt": "p", "retry": "r"}})
    assert withtext["recoverable"]["prompt"] == rb.digest(["p", "r"])
    assert "prompt" not in withtext["unrecoverable"]


# --- データとタスクの組 ----------------------------------------------------


def all_suites():
    # tasks.json を持つものだけが組。__pycache__ のような副産物は数えない。
    return sorted(d.name for d in (rb.SUITES_DIR).iterdir()
                  if d.is_dir() and (d / "tasks.json").is_file())


@check("組: suites/ 配下がすべて読める")
def _():
    names = all_suites()
    assert names, "組が1つも無い"
    for name in names:
        tasks, conditions, _ = rb.load_suite(name)
        assert tasks, name
        assert len(conditions) >= 2, (name, list(conditions))


@check("組: 正答が採点規則で取り出せる形になっている")
def _():
    for name in all_suites():
        tasks, _, _ = rb.load_suite(name)
        for t in tasks:
            extracted = rb.normalize_truth(t["ground_truth"])
            assert extracted == str(t["ground_truth"]), (name, t["task_id"], extracted)


def records_of(data):
    """条件が指すレコード。計器v2 は文書の変種を並べて持つので、その先を見る。"""
    if isinstance(data, dict) and isinstance(data.get("variants"), list):
        return data["variants"][0]["records"]
    return data["records"] if isinstance(data, dict) else data


def is_level_ladder(name):
    """水準梯子の組かどうか。計器v2（分布プローブ）は梯子ではないので外す。"""
    _, _, spec = rb.load_suite(name)
    return all("level" in c for c in spec)


@check("組: すべての条件が同じ件数のレコードを指している")
def _():
    for name in all_suites():
        _, conditions, _ = rb.load_suite(name)
        counts = {c: len(records_of(d)) for c, d in conditions.items()}
        assert len(set(counts.values())) == 1, (name, counts)
        for cname, data in conditions.items():
            if isinstance(data, dict) and isinstance(data.get("variants"), list):
                sizes = {len(v["records"]) for v in data["variants"]}
                assert len(sizes) == 1, (name, cname, sizes)


@check("組: 最下位の条件に単位・業種名・活動状態の語が現れない")
def _():
    # 明示してしまうと条件の差が消える。禁止語を置いて後退を検出する。
    # 検査対象は各組の先頭の条件（もっとも自己記述性が低い側）。
    forbidden = ["百万円", "情報通信", "製造業", "unit", "active", "revenue", "industry"]
    for name in all_suites():
        if not is_level_ladder(name):
            continue
        _, conditions, _ = rb.load_suite(name)
        first = next(iter(conditions.values()))
        text = json.dumps(first, ensure_ascii=False)
        for word in forbidden:
            assert word not in text, (name, word)


@check("組: 水準の仕様が機械可読に残っている")
def _():
    for name in all_suites():
        _, conditions, spec = rb.load_suite(name)
        assert [s["name"] for s in spec] == list(conditions), name
        path = rb.suite_dir(name)
        if not (path / "conditions.json").is_file():
            continue
        # conditions.json のある組は、置いたものを条件ごとに書いてあること。
        # 梯子は「何を置いたか」（placed）、計器v2 は格子の座標と偶然水準。
        for entry in spec:
            assert (path / entry["file"]).is_file(), (name, entry["file"])
            if is_level_ladder(name):
                assert "placed" in entry, (name, entry["name"])
            else:
                for key in ("t", "d", "arm", "gamma"):
                    assert key in entry, (name, entry["name"], key)


@check("組: 3条件以上の組でも集計と描画が通る")
def _():
    for name in all_suites():
        _, conditions, _ = rb.load_suite(name)
        if len(conditions) <= 2:
            continue
        rows = [
            fake_row(name, condition, success=(i % 2 == 0), total=1000 + 100 * i, attempts=1 + i % 3)
            for i, condition in enumerate(conditions)
        ]
        run = {"results": rows, "conditions": list(conditions), "repeats": 1, "max_attempts": 3}
        text = summarize.render(summarize.summarize(run))
        assert isinstance(text, str) and text


@check("組: 存在しない組を指定したら止まる")
def _():
    try:
        rb.load_suite("no_such_suite")
    except SystemExit as exc:
        assert "見つかりません" in str(exc), exc
    else:
        raise AssertionError("存在しない組が受理された")


# --- 反復 ----------------------------------------------------------------


@check("反復: 反復番号が行に残る")
def _():
    rows = run_repeats("mock-reasoning", repeats=3)
    assert [r["repeat"] for r in rows] == [1, 2, 3]


@check("反復: 既定値は5")
def _():
    assert rb.REPEATS == 5, rb.REPEATS


def run_main(*argv):
    """引数を与えて main() を呼ぶ。入口の検証を踏むためだけに使う。"""
    saved = sys.argv
    sys.argv = ["run_benchmark.py", "--mock", "--no-save", *argv]
    try:
        return rb.main()
    finally:
        sys.argv = saved


@check("反復: --repeats 0 は既定値に化けず弾かれる")
def _():
    try:
        run_main("--repeats", "0")
    except SystemExit as exc:
        assert "1以上" in str(exc), exc
    else:
        raise AssertionError("--repeats 0 が受理された")


@check("反復: --max-attempts 0 も既定値に化けず弾かれる")
def _():
    try:
        run_main("--max-attempts", "0")
    except SystemExit as exc:
        assert "1以上" in str(exc), exc
    else:
        raise AssertionError("--max-attempts 0 が受理された")


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


@check("seed: 反復ごとに違う値を送り、規則と実際の値を記録する")
def _():
    # 全反復に同じ seed を送ると、seed を実際に効かせるサーバでは反復が
    # 同じ出力になり、ばらつきを測るという設計が成り立たない。
    assert rb.seed_for_repeat(1) == rb.SEED
    assert rb.seed_for_repeat(3) == rb.SEED + 2
    seeds = [rb.sampling_params(r)["seed"] for r in (1, 2, 3, 4, 5)]
    assert len(set(seeds)) == 5, seeds

    # 投げる直前に当てているか。落とされていれば当てない。
    sent = []

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    sent.append(kwargs.get("seed"))
                    raise RuntimeError("ここまで来れば十分")

    sampling = {"requested": rb.sampling_params(), "used": rb.sampling_params(), "dropped": {}}
    for repeat in (1, 2, 3):
        try:
            rb.create_completion(FakeClient(), "m", [], sampling, repeat)
        except RuntimeError:
            pass
    assert sent == [rb.SEED, rb.SEED + 1, rb.SEED + 2], sent

    dropped = {"requested": rb.sampling_params(), "used": {"temperature": 1.0}, "dropped": {}}
    sent.clear()
    try:
        rb.create_completion(FakeClient(), "m", [], dropped, 2)
    except RuntimeError:
        pass
    assert sent == [None], sent


@check("エラーの二分: 測定の結果は引き継ぎ、基盤の失敗は回し直す")
def _():
    ctx = ("BadRequestError: Error code: 400 - This model's maximum context "
           "length is 65536 tokens.")
    got = ("NotFoundError: Error code: 404 - The model "
           "`allenai/Olmo-3-7B-Think` does not exist.")
    assert rb.classify_error(ctx) == "measurement"
    assert rb.classify_error(got) == "infrastructure"
    assert rb.classify_error("APIConnectionError: Connection error.") == "infrastructure"
    assert rb.classify_error(None) is None

    # 途中経過を読むとき、基盤側のエラー行だけが落ちる
    fp = {"suite": "x", "settings": {"repeats": 4}}
    rows = [
        {"repeat": 1, "status": "ok", "error": None},
        {"repeat": 2, "status": "error", "error": ctx, "error_class": "measurement"},
        {"repeat": 3, "status": "error", "error": got, "error_class": "infrastructure"},
        # error_class を持たない古い行も、文面から分け直せる
        {"repeat": 4, "status": "error", "error": got},
    ]
    fd, name = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps({"header": fp}) + chr(10))
        for r in rows:
            f.write(json.dumps(r) + chr(10))
    try:
        kept = rb.load_partial(pathlib.Path(name), fp)
    finally:
        os.unlink(name)
    assert [r["repeat"] for r in kept] == [1, 2], [r["repeat"] for r in kept]


@check("計器v2: 偶然水準 gamma が仕様の値と一致する")
def _():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "build_v4", pathlib.Path(__file__).resolve().parent / "suites" / "build_v4.py")
    b4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b4)
    # 仕様（paper/notes/instrument-v2-distribution-probe.md 第4節）が挙げている例
    assert abs(b4.gamma(0, 0) - 1 / 15) < 1e-12
    assert abs(b4.gamma(0, 4) - 1.0) < 1e-12
    assert abs(b4.gamma(1, 3) - 0.5) < 1e-12
    assert abs(b4.gamma(0, 2) - 1 / 6) < 1e-12      # スモークで使うセル
    assert b4.gamma(2, 0) == 1.0                     # 的が全部書いてある


@check("計器v2: 変種は反復番号で巡回し、固定側は動かない")
def _():
    data = {"variants": ["A", "B", "C"]}
    assert [rb.pick_variant(data, r) for r in (1, 2, 3, 4)] == [
        ("A", 0), ("B", 1), ("C", 2), ("A", 0)]
    fixed = {"variants": ["only"]}
    assert [rb.pick_variant(fixed, r)[1] for r in (1, 2, 3)] == [0, 0, 0]
    # 変種を持たない v3 の条件は素通しする
    plain = {"records": [1, 2]}
    assert rb.pick_variant(plain, 5) == (plain, None)


@check("計器v2: 山推定は数を先に決めず、隙間で切る")
def _():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sv4", pathlib.Path(__file__).resolve().parent / "summarize_v4.py")
    sv4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sv4)
    # 固まっていれば1つ
    assert len(sv4.cluster([228, 228, 228])) == 1
    # 離れていれば分かれる
    groups = sv4.cluster([228, 228, 1717, 1717])
    assert len(groups) == 2, groups
    # 全部ばらけると山も増える
    assert len(sv4.cluster([100, 500, 900, 1300])) == 4
    # 散らばりは、固まれば 0、二分すれば 1 ビット
    assert sv4.entropy([10]) == 0.0
    assert abs(sv4.entropy([5, 5]) - 1.0) < 1e-12


@check("計器v2: 0回答を数え分ける（山推定は変えない）")
def _():
    import importlib.util
    root = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("sv4", root / "summarize_v4.py")
    sv4 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sv4)
    rows = [{"final_number": v, "total_tokens": 10, "status": "ok"}
            for v in (0, 0, 228, 186, 186)]
    d = sv4.describe(rows, 228, 1 / 6)
    assert d["0回答数"] == 2, d["0回答数"]
    # 0 は山からは外さない（値として数直線に載る）
    assert sum(m["件数"] for m in d["山"]) == 5
    assert d["正解山の占有率"] == 1 / 5


@check("計器v2: 色は数値の規則だけで決まる")
def _():
    import importlib.util
    root = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("v4g", root / "v4_grid.py")
    v4g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v4g)
    assert v4g.verdict(0.50, 0.167) == "above"
    assert v4g.verdict(0.00, 0.167) == "below"
    assert v4g.verdict(0.20, 0.167) == "near"      # ±0.05 以内
    assert v4g.verdict(0.10, 0.167) == "below"
    # 同じ座標に両腕があれば、既定の「振る」を出す
    cells = {"a": {"t": 0, "d": 2, "arm": "fixed"}, "b": {"t": 0, "d": 2, "arm": "varied"}}
    assert v4g.cell_at(cells, 0, 2)["arm"] == "varied"


@check("計器v2: 可読出力が外部を読まない一枚になっている")
def _():
    import importlib.util
    import re
    root = pathlib.Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("v4g", root / "v4_grid.py")
    v4g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v4g)
    run = {"run_at": "T", "models": ["m"], "thinking_mode": "on", "max_attempts": 1,
           "repeats": 2, "fingerprint": {"inputs": "abc"},
           "inputs": {"tasks": [{"ground_truth": "228"}]},
           "condition_spec": [{"name": "c", "t": 0, "d": 2, "arm": "varied", "gamma": 1 / 6}],
           "results": [{"condition": "c", "status": "ok", "final_answer": "228",
                        "total_tokens": 10, "repeat": 1},
                       {"condition": "c", "status": "ok", "final_answer": "0",
                        "total_tokens": 10, "repeat": 2}]}
    page = v4g.render_html(run, v4g.collect(run))
    # CDN も外部 JS も読まない。単体で開ける。
    assert not re.search(r"(?i)(<script|src=|href=[\"']http|@import|url\(http)", page), "外部参照がある"
    assert "<style>" in page and "凡例" in page
    # 壊れ方の型のラベルは付けない（帰属判断を混ぜない）
    for word in ("散る", "割れる", "ずれる"):
        assert word not in page, word


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
