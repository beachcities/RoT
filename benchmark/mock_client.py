"""HTTP を一切叩かないダミークライアント。

`run_benchmark.py --mock` から使う。APIキーを置く前に、ランナー側のコード経路
（リトライの累積、reasoning_tokens が返らない場合、usage 自体が無い場合、
途中で例外が出た場合）を実データなしで一通り踏むためのもの。

各シナリオはモデル名で選ぶ。応答の中身はデータ条件（raw / self_descriptive）を
見ない。「自己記述性が高いほうが少ない試行で解ける」かどうかはこれから測る対象
であって、フィクスチャに書き込んでよい前提ではないため。
唯一の例外は `mock-varied`（下記）で、そこでも仮説とは逆向きの値を意図的に
置いてある。集計表の書式を確認するための任意の値であり、予測ではない。
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from types import SimpleNamespace

BASE_DIR = Path(__file__).resolve().parent


class MockAPIError(RuntimeError):
    """SDK 例外の代わり。ランナー側は Exception を捕捉する。"""


def _usage(prompt_tokens, completion_tokens, reasoning_tokens=None, details="object"):
    """usage オブジェクトを組み立てる。

    details:
      "object" -- completion_tokens_details を属性アクセス可能なオブジェクトで返す
      "dict"   -- 素の dict で返す（OpenAI互換サーバに実在する形）
      "absent" -- completion_tokens_details 自体を持たない（reasoning は取得不能）
    """
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )
    if details == "object":
        usage.completion_tokens_details = SimpleNamespace(reasoning_tokens=reasoning_tokens)
    elif details == "dict":
        usage.completion_tokens_details = {"reasoning_tokens": reasoning_tokens}
    return usage


def _response(content, usage):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=usage,
    )


def _load_ground_truth(first_user_message):
    """プロンプトに埋まっている query から、そのタスクの正答を引く。

    どの組（suite）で走っているかはモック側に渡ってこないので、全部の組の
    tasks.json を舐めて query 文字列で突き合わせる。
    """
    for path in sorted((BASE_DIR / "suites").glob("*/tasks.json")):
        with open(path, encoding="utf-8") as f:
            for task in json.load(f):
                if task["query"] in first_user_message:
                    return task["ground_truth"]
    return None


def _detect_condition(first_user_message):
    """フィクスチャの分岐用。データ条件を機械的に見分けるだけの処理。"""
    return "self_descriptive" if "unit_definition" in first_user_message else "raw"


# --- シナリオ ------------------------------------------------------------
# 各シナリオは (ctx) -> response。ctx.attempt は1始まり。


def _correct(ctx):
    return ctx.truth or "0"


def _wrong(ctx):
    return "850"


def s_reasoning(ctx):
    """reasoning_tokens を返すモデル。1回目で正答。"""
    return _response(_correct(ctx), _usage(420, 260, reasoning_tokens=200))


def s_no_reasoning(ctx):
    """completion_tokens_details を持たないモデル。reasoning は null になるはず。"""
    return _response(_correct(ctx), _usage(420, 60, details="absent"))


def s_reasoning_zero(ctx):
    """reasoning_tokens=0 を返すモデル。null ではなく 0 として記録されるはず。"""
    return _response(_correct(ctx), _usage(420, 60, reasoning_tokens=0))


def s_dict_usage(ctx):
    """completion_tokens_details が dict のサーバ。"""
    return _response(_correct(ctx), _usage(420, 260, reasoning_tokens=200, details="dict"))


def s_no_usage(ctx):
    """usage を返さないサーバ。トークンが計測できないので ROT は算出できない。"""
    return _response(_correct(ctx), None)


def s_retry(ctx):
    """2回外して3回目に正答。失敗試行のトークンが分母に積まれるはず。"""
    if ctx.attempt < 3:
        return _response(_wrong(ctx), _usage(420 + 40 * ctx.attempt, 150, reasoning_tokens=120))
    return _response(_correct(ctx), _usage(500, 130, reasoning_tokens=90))


def s_always_wrong(ctx):
    """MAX_ATTEMPTS まで外し続ける。success=False、ROT=0。"""
    return _response(_wrong(ctx), _usage(420 + 40 * ctx.attempt, 180, reasoning_tokens=150))


def s_mixed_reasoning(ctx):
    """1回目は reasoning を返し、2回目は返さない。内訳は不明として扱われるはず。"""
    if ctx.attempt == 1:
        return _response(_wrong(ctx), _usage(420, 260, reasoning_tokens=200))
    return _response(_correct(ctx), _usage(500, 60, details="absent"))


def s_empty(ctx):
    """本文が空で返る（推論枠を使い切ったモデルで起きる）。"""
    if ctx.attempt == 1:
        return _response("", _usage(420, 300, reasoning_tokens=300))
    return _response(_correct(ctx), _usage(520, 50, reasoning_tokens=10))


def s_verbose(ctx):
    """指示を無視して文章で返す。採点規則（最後の数値を採る）を踏む。"""
    return _response(
        f"該当は1社です。2024年度の売上高は {ctx.truth} 円です。",
        _usage(420, 80, reasoning_tokens=20),
    )


def s_fullwidth(ctx):
    """全角数字で返す。正規化（NFKC）を踏む。"""
    body = unicodedata.normalize("NFKC", ctx.truth or "0")
    wide = "".join(chr(ord(c) + 0xFEE0) if c.isdigit() else c for c in body)
    return _response(wide, _usage(420, 60, reasoning_tokens=10))


def s_inconsistent_usage(ctx):
    """reasoning が completion を上回る、あり得ない内訳を返すサーバ。"""
    return _response(_correct(ctx), _usage(420, 30, reasoning_tokens=150))


def s_error(ctx):
    """1回目から通信が失敗する。"""
    raise MockAPIError("mock: connection reset by peer")


def s_error_midway(ctx):
    """1回目は応答し、2回目で落ちる。既に消費したトークンが残るかを見る。"""
    if ctx.attempt == 1:
        return _response(_wrong(ctx), _usage(420, 260, reasoning_tokens=200))
    raise MockAPIError("mock: 429 rate limit exceeded")


def s_noisy(ctx):
    """反復ごとに消費が揺れるモデル。ばらつきの表示を確かめるためのもの。

    揺れ幅は任意の固定値。データ条件では変えていない。
    """
    jitter = (0, 90, -40, 150, -20)[(ctx.repeat - 1) % 5]
    return _response(_correct(ctx), _usage(420, 260 + jitter, reasoning_tokens=200 + jitter))


def s_flaky(ctx):
    """反復のうち何回かだけ解けるモデル。正答数 n/N の表示を確かめる。

    奇数回目だけ解ける。データ条件では変えていない。
    """
    if ctx.repeat % 2 == 1:
        return _response(_correct(ctx), _usage(420, 200, reasoning_tokens=150))
    return _response(_wrong(ctx), _usage(420 + 40 * ctx.attempt, 180, reasoning_tokens=150))


def s_varied(ctx):
    """データ条件で試行回数が変わるフィクスチャ。集計表の書式確認用。

    値は任意であり、仮説（自己記述性を高めるとROTが改善する）とは逆向きに
    置いてある。集計の出力を実測結果と読み違えないようにするため。
    """
    needed = 1 if ctx.condition == "raw" else 2
    if ctx.attempt < needed:
        return _response(_wrong(ctx), _usage(600, 220, reasoning_tokens=180))
    return _response(_correct(ctx), _usage(600, 160, reasoning_tokens=120))


SCENARIOS = {
    "mock-reasoning": s_reasoning,
    "mock-no-reasoning": s_no_reasoning,
    "mock-reasoning-zero": s_reasoning_zero,
    "mock-dict-usage": s_dict_usage,
    "mock-no-usage": s_no_usage,
    "mock-retry": s_retry,
    "mock-always-wrong": s_always_wrong,
    "mock-mixed-reasoning": s_mixed_reasoning,
    "mock-empty": s_empty,
    "mock-verbose": s_verbose,
    "mock-inconsistent-usage": s_inconsistent_usage,
    "mock-fullwidth": s_fullwidth,
    "mock-error": s_error,
    "mock-error-midway": s_error_midway,
    "mock-noisy": s_noisy,
    "mock-flaky": s_flaky,
    "mock-varied": s_varied,
}

DEFAULT_MOCK_MODELS = list(SCENARIOS)


class _Completions:
    def __init__(self, owner):
        self._owner = owner

    def create(self, *, model, messages, **kwargs):
        return self._owner._create(model, messages, kwargs)


class MockClient:
    """OpenAI クライアントのうち、ランナーが使う部分だけを模したもの。"""

    def __init__(self):
        self.chat = SimpleNamespace(completions=_Completions(self))
        self.calls = []
        # 反復番号はランナーから渡ってこないので、会話の1通目が来た回数で数える。
        # そうしておけばランナー側にモック専用の受け口を作らずに済む。
        self._repeats = {}

    def _create(self, model, messages, kwargs):
        scenario = SCENARIOS.get(model)
        if scenario is None:
            raise MockAPIError(
                f"mock: unknown model {model!r}. "
                f"available: {', '.join(sorted(SCENARIOS))}"
            )

        user_messages = [m for m in messages if m.get("role") == "user"]
        first = user_messages[0]["content"] if user_messages else ""
        attempt = len(user_messages)
        condition = _detect_condition(first)
        key = (model, condition)
        if attempt == 1:
            self._repeats[key] = self._repeats.get(key, 0) + 1
        ctx = SimpleNamespace(
            model=model,
            attempt=attempt,
            repeat=self._repeats.get(key, 1),
            condition=condition,
            truth=_load_ground_truth(first),
            messages=messages,
        )
        self.calls.append((model, condition, ctx.repeat, attempt))
        return scenario(ctx)
