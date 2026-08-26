"""ROT benchmark: measure token cost per outcome across data conditions.

Runs each task under two data conditions (raw / self-descriptive) for each
model, retrying on failure up to MAX_ATTEMPTS. Tokens from failed attempts are
included in the denominator: the size of the search is itself the weight of the
context that was missing from the data.

See README.md for what this does and does not measure.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

import summarize

BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "results"
PARTIAL_DIR = RESULTS_DIR / "partial"
SUITES_DIR = BASE_DIR / "suites"

# .env はこのファイルの隣を見る。リポジトリ直下から起動されても拾えるように。
load_dotenv(BASE_DIR / ".env")


# 指紋の桁数。衝突を心配する用途ではなく、どの入力で出た結果かを突き合わせる用途。
FINGERPRINT_BITS = 16


def digest(obj):
    """JSON化できるものの内容ハッシュ。

    キーの順序は保つ（レコードの項目順は水準の定義そのものなので、順序が
    変われば別の入力である）。整形の違いでは変わらないよう、区切りは詰める。
    """
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:FINGERPRINT_BITS]


def file_digest(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:FINGERPRINT_BITS]
    except OSError:
        return None


def sdk_version():
    if MOCK_ONLY_SDK[0]:
        return "mock（HTTPクライアントを読み込んでいない）"
    try:
        import openai

        return getattr(openai, "__version__", None)
    except ImportError:
        return None


MOCK_ONLY_SDK = [False]


def git_state():
    """コミットと、benchmark/ に未コミットの変更があるか。

    「作業ツリーを編集しながら回した結果」を後から見分けるために要る。
    git が無い場所でも落ちないようにしておく。
    """
    def run(args):
        try:
            out = subprocess.run(
                ["git", *args], cwd=BASE_DIR, capture_output=True, text=True, timeout=10
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout.strip() if out.returncode == 0 else None

    commit = run(["rev-parse", "HEAD"])
    status = run(["status", "--porcelain", "--", str(BASE_DIR)])
    return {
        "commit": commit,
        # None は「判定できなかった」。False と区別する。
        "dirty": None if status is None else bool(status),
    }


def partial_path(fingerprint):
    """途中経過の置き場所。**ファイル名が設定の指紋そのもの**になっている。

    入力・プロンプト・サンプリング・コードのどれかが変われば別のファイルになるので、
    違う条件のランが混ざることがない。再開の可否を別途判定する必要もない。
    """
    return PARTIAL_DIR / f"partial_{digest(fingerprint)}.jsonl"


def trial_key(result):
    return (result["model"], result["condition"], result["task_id"], result["repeat"])


def load_partial(path, fingerprint):
    """途中経過を読む。無ければ空。

    先頭行に指紋を書いてあるので、ファイル名の一致に加えて中身でも突き合わせる。
    壊れた行（書き込み中に落ちた場合の最終行など）は捨てる。
    """
    if not path.is_file():
        return []
    done = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                print(f"  途中経過の {i + 1} 行目が壊れていたので捨てた")
                continue
            if i == 0:
                if row.get("header") != fingerprint:
                    raise SystemExit(
                        f"途中経過 {path.name} の指紋が現在の設定と一致しません。"
                        "別の条件のランです。--no-resume で新しく始めるか、"
                        "そのファイルを退けてください。"
                    )
                continue
            done.append(row)

    # **基盤の都合で落ちた試行は引き継がない。** 測定の結果であるエラー
    # （文脈長超過）はそのまま残す。分類は各行の error_class にある。
    # 古い途中経過には error_class が無いので、その場で文面から分け直す。
    kept, retry = [], 0
    for row in done:
        # 落とす対象は「エラーで終わった」と明示されている行だけ。それ以外は
        # 判断材料が無いので触らない。
        if row.get("status") != "error":
            kept.append(row)
            continue
        kind = row.get("error_class") or classify_error(row.get("error"))
        if kind == "measurement":
            kept.append(row)
        else:
            retry += 1
    if retry:
        print(f"  基盤側のエラーで終わっていた {retry} 件は引き継がず、回し直す")
    return kept


def append_partial(path, fingerprint, result):
    """1試行ぶんを書き足す。落ちてもここまでは残る。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file()
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(json.dumps({"header": fingerprint}, ensure_ascii=False) + chr(10))
        f.write(json.dumps(result, ensure_ascii=False) + chr(10))
        f.flush()
        os.fsync(f.fileno())


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
# データとタスクの組。組ごとに raw / self_descriptive / tasks が揃っている。
# どの組を使ったかは結果JSONに残す。組が違えば数値は比較できない。
SUITE = os.getenv("SUITE", "v3_levels")

# 実行経路の覚え書き。どこで・どう回したかは結果から機械的には分からないので、
# 呼び出す側が書く（Colab のノートブック名、GPU、vLLM の起動オプションなど）。
# 空なら空のまま残す。後から推測で埋めない。
RUN_ROUTE = os.getenv("RUN_ROUTE", "")

# 中間推論を働かせるかどうか。off にすると chat_template_kwargs で
# enable_thinking=False を送る（Qwen 系など、切り替えを持つモデル向け）。
# 同じモデル・同じ課題で、考えさせた場合と考えさせない場合を比べるために要る。
#
# **切り替えは指紋に入れる。** on と off は別の測定なので、混ざってはいけない。
# 途中経過の置き場所も指紋から決まるので、片方の続きにもう片方が積まれることはない。
THINKING = os.getenv("THINKING", "on").strip().lower()
if THINKING not in ("on", "off"):
    raise SystemExit(f"環境変数 THINKING は on か off である必要があります: {THINKING!r}")


def thinking_body():
    """chat_template_kwargs に載せるもの。on のときは何も送らない（既定に任せる）。"""
    if THINKING == "off":
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {}


def env_float(name, default):
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        raise SystemExit(f"環境変数 {name} は数値である必要があります: {raw!r}")


# サンプリング設定。ここまでのランは指定せず SDK/サーバの既定値に任せていた。
# 明示して記録する。値は既定値（temperature=1）に揃えてあり、これまでの測定と
# 揃えるためのもの。0 にすると反復のばらつきがほぼ消えるので、ばらつきを見る
# という設計と噛み合わない。seed は best-effort で、決定性の保証ではない。
TEMPERATURE = env_float("TEMPERATURE", 1.0)
TOP_P = env_float("TOP_P", 1.0)
SEED = env_int("SEED", 20260820)

# 1リクエストで生成できる上限。0 なら送らない（サーバの既定に任せる）。
#
# 推論モデルは、書かれていない対応関係を推し量ろうとすると思考が発散する
# （実測: Olmo-3-7B-Think が1試行で 52,625 字を書いた）。**その様子がそのまま
# 残ることがこの測定の目的なので、短く切ってはいけない。** 切れば、切った位置が
# 測定値を決めてしまう。試行上限10と同じ性質の制約が生成長にも入ることになる。
#
# ただし無制限にはできないので、十分大きい値を置いたうえで、そこに到達した件数を
# 記録して区別する。到達した試行は集計から除外しない。
MAX_OUTPUT_TOKENS = env_int("MAX_OUTPUT_TOKENS", 0)


# 反復ごとの seed の導出規則。**反復は独立な標本でなければ意味がない。**
# 全反復に同じ seed を送ると、vLLM のように seed を実際に効かせるサーバでは
# 1回目と2回目が同じ出力になり、ばらつきを測るという設計が成り立たない。
# 反復番号から導出して、反復ごとに違う seed を送る。
#
#     seed = SEED + (repeat - 1)
#
# repeat=1 は SEED そのものなので、REPEATS=1 の既存ランと送る値は変わらない。
SEED_RULE = "seed = SEED + (repeat - 1)"


def seed_for_repeat(repeat):
    return SEED + (repeat - 1)


def sampling_params(repeat=1):
    params = {"temperature": TEMPERATURE, "top_p": TOP_P, "seed": seed_for_repeat(repeat)}
    if MAX_OUTPUT_TOKENS > 0:
        params["max_tokens"] = MAX_OUTPUT_TOKENS
    return params

# プロンプトは prompts.json に外出しした。文言を変えると結果が動くことが実測
# されている（「数値のみ出力」と縛ると探索が起きず raw は正答0だった、
# リトライ文言が「読み直して」だと同じ読みを繰り返した）。条件間の差が言い回し
# に依存していないかを確かめられるよう、言い換えを選べるようにしてある。
# 投げた全文は結果JSONに残す。
PROMPTS_PATH = BASE_DIR / "prompts.json"
PROMPT_SET = os.getenv("PROMPT", "p1_baseline")

# 本文が空で返ったとき、履歴に空文字を積むと拒否するサーバがあるための代替。
EMPTY_ANSWER_PLACEHOLDER = "(応答なし)"

# 反復ごとの明細をそのまま並べると読めなくなるので、この件数を超えたら省略する。
TRIAL_TABLE_LIMIT = 30


def build_client(mock=False):
    """Return the API client. --mock swaps in a stand-in that never uses HTTP."""
    if mock:
        from mock_client import MockClient

        MOCK_ONLY_SDK[0] = True
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


def load_prompts(name):
    """プロンプト一式を読む。raw / self_descriptive で切り替えることはしない。"""
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        sets = json.load(f)
    available = [k for k in sets if not k.startswith("_")]
    if name not in available:
        raise SystemExit(f"プロンプト {name!r} が見つかりません。あるのは: {', '.join(available)}")
    chosen = sets[name]
    for key in ("prompt", "retry"):
        if key not in chosen:
            raise SystemExit(f"プロンプト {name!r} に {key} がありません")
    for field in ("{data}", "{query}"):
        if field not in chosen["prompt"]:
            raise SystemExit(f"プロンプト {name!r} の prompt に {field} がありません")
    return chosen


def suite_dir(name):
    path = SUITES_DIR / name
    if not path.is_dir():
        available = ", ".join(sorted(p.name for p in SUITES_DIR.iterdir() if p.is_dir()))
        raise SystemExit(f"組 {name!r} が見つかりません。あるのは: {available}")
    return path


# 二値（raw / self_descriptive）の組の既定の中身。conditions.json があればそちらが優先。
LEGACY_CONDITIONS = [
    {"name": "raw", "file": "raw_dataset.json"},
    {"name": "self_descriptive", "file": "self_descriptive_dataset.json"},
]


def load_suite(name):
    """組を読む。データ条件はすべて同じ世界・同じタスクを指していること。

    conditions.json があれば、そこに書かれた順で任意個の条件を読む。各条件に
    何を置いたか（水準の仕様）も一緒に返し、結果JSONにそのまま残す。
    """
    path = suite_dir(name)
    tasks = load_json(path / "tasks.json")
    manifest_path = path / "conditions.json"
    spec = load_json(manifest_path)["conditions"] if manifest_path.is_file() else LEGACY_CONDITIONS
    conditions = {}
    for entry in spec:
        if entry["name"] in conditions:
            raise SystemExit(f"組 {name!r} の条件名が重複しています: {entry['name']}")
        conditions[entry["name"]] = load_json(path / entry["file"])
    return tasks, conditions, spec


def numbers_in(text):
    """文字列から整数の並びをすべて取り出す。

    桁区切りのコンマは数字に挟まれているものだけを落とす。空白は落とさない。
    まとめて空白を消すと、改行で隔てられた別々の数値が1つに繋がってしまう
    （実測: 「1,860,000,000

1860000000」が 18600000001860000000 になり、
    正答を誤答と判定していた）。
    """
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"(?<=\d),(?=\d)", "", normalized)
    return re.findall(r"\d+", normalized)


def extract_number(text):
    """回答から採点対象の数値を取り出す。

    採点規則（結果に効くので明示しておく）:
      1. NFKC で正規化する（全角数字を半角に落とす）
      2. 桁区切りのコンマ（数字に挟まれたもの）だけを落とす
      3. 空でない最後の行を見て、そこにある最後の整数を答えとみなす
      4. 最後の行に数値が無ければ、本文全体の最後の整数を採る

    プロンプトが「最後の行には数値のみ」と指示しているので、まず最後の行を見る。
    最初の数値を採ると「該当は1社です。売上は1200000000円です」の 1 を拾って
    誤答扱いになる。誤答扱いはリトライを誘発して分母を膨らませるため、測ろうと
    している量そのものを歪める。抽出結果は attempt_log に extracted として残し、
    後から採点をやり直せるようにする。
    """
    if not text:
        return None
    lines = [line for line in text.splitlines() if line.strip()]
    for candidate in ([lines[-1]] if lines else []) + [text]:
        matches = numbers_in(candidate)
        if matches:
            return matches[-1].lstrip("0") or "0"
    return None


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


# エラーの二分。**測定の結果であるエラーと、基盤の都合で起きたエラーは別物。**
#
# 文脈長を超えて 400 になるのは、その水準でモデルが払った消費の帰結であって、
# 測定の結果である。引き継いで最終結果に残す（条件を変えて避けない）。
#
# 404・接続断・サーバの取り違えは測定の結果ではない。**引き継ぐと、基盤の失敗が
# 結果として固まってしまう。** 再開時に消して、もう一度回す。実測: 煙試験で
# 前段のサーバが生き残り、2モデル目の全試行が 404 になった。あれを引き継いだら
# 「Olmo は解けなかった」という記録になる。
MEASUREMENT_ERROR_MARKS = (
    "maximum context length",
    "reduce the length of the input prompt",
    "context length",
)


def classify_error(text):
    """エラーの文面を measurement / infrastructure に分ける。

    **判別できないものは infrastructure に寄せる。** 取りこぼして再実行する損は
    Pod の数分だが、基盤の失敗を測定結果として残す損は取り返せない。
    """
    if not text:
        return None
    low = str(text).lower()
    if any(mark in low for mark in MEASUREMENT_ERROR_MARKS):
        return "measurement"
    return "infrastructure"


def unsupported_param(exc, kwargs):
    """例外がどのパラメータを拒んでいるかを返す。分からなければ None。

    モデルによっては temperature や seed を受け付けない。落とさずに黙って
    通すと「指定したつもりの設定」が記録と食い違うので、落としたことを残す。
    """
    text = f"{type(exc).__name__}: {exc}"
    if not any(w in text.lower() for w in
               ("unsupported", "unrecognized", "not supported", "invalid_request", "does not support")):
        return None
    for name in kwargs:
        if name in text:
            return name
    return None


def create_completion(client, model, messages, sampling, repeat=1, seed=None):
    """sampling を付けて投げる。拒まれたものは落として記録し、投げ直す。

    thinking を切る指定は落とさない。**落として黙って続けると、考えさせない
    つもりの測定が考えさせた測定になる。** 拒まれたらそこで止める。
    """
    extra = thinking_body()
    while True:
        try:
            kwargs = dict(sampling["used"])
            # seed はモデルごとの共有状態ではなく、反復ごとに決まる。
            # サーバに拒まれて落とされていれば "used" に無いので、当てない。
            if "seed" in kwargs:
                kwargs["seed"] = seed_for_repeat(repeat) if seed is None else seed
            if extra:
                kwargs["extra_body"] = extra
            return client.chat.completions.create(model=model, messages=messages, **kwargs)
        except Exception as exc:
            if extra and "enable_thinking" in f"{exc}":
                raise SystemExit(
                    "THINKING=off を指定しましたが、サーバが enable_thinking を"
                    f"受け付けませんでした。測定として成立しないので止めます: {exc}"
                )
            name = unsupported_param(exc, sampling["used"])
            if name is None:
                raise
            sampling["dropped"][name] = f"{type(exc).__name__}: {exc}"[:300]
            sampling["used"] = {k: v for k, v in sampling["used"].items() if k != name}


# 推論部分の取り出し方は三通りある。
#   1. reasoning_content に分けて返る（--reasoning-parser 付きのサーバ）
#   2. 開始タグと終了タグが対で本文に現れる
#   3. 終了タグだけが現れる（開始タグはチャットテンプレート側にある）
# 3 は Olmo-3-7B-Think で実際に踏んだ形。拾い損ねると、思考を含んだ本文が
# そのまま会話履歴に積まれ、数試行で文脈長を使い切る（実測: 5〜8試行で 16k 超過）。
#
# 系統ごとにタグが違うので、対を並べて持つ。新しい系統を足すときはここに1行足す
# （→ LOCAL_MODELS.md「新しいモデル系統を足す手順」）。
THINK_TAGS = [
    ("<think>", "</think>"),                      # Qwen3.x / Olmo 3 / DeepSeek-R1 系
    ("<thinking>", "</thinking>"),
    ("<reasoning>", "</reasoning>"),
    ("<|begin_of_thought|>", "<|end_of_thought|>"),
]


def _tag_pair_patterns():
    for open_tag, close_tag in THINK_TAGS:
        yield close_tag, re.compile(
            re.escape(open_tag) + r"(.*?)" + re.escape(close_tag) + r"\s*", re.S
        )


def split_thinking(message):
    """(思考テキスト, 最終本文, どの経路で取れたか) を返す。

    経路は "reasoning_content" / "tag_pair" / "closing_tag" / None。
    **どれで取れたかを結果に残す。** 系統によって形が違うので、後から
    「この値はどうやって取ったのか」が分からないと突き合わせられない。

    長さだけでなくテキストそのものを残す。何を推し量っていたかは、
    トークン数からは分からない。
    """
    content = (getattr(message, "content", None) or "")
    thinking = getattr(message, "reasoning_content", None)
    if thinking is None and isinstance(message, dict):
        thinking = message.get("reasoning_content")
    if thinking:
        return thinking, content.strip(), "reasoning_content"

    for close_tag, pattern in _tag_pair_patterns():
        matches = pattern.findall(content)
        if matches:
            joined = chr(10).join(m.strip() for m in matches)
            return joined, pattern.sub("", content).strip(), "tag_pair"

    # 開始タグがプロンプト側にあり、生成には終了タグしか現れない場合
    for _, close_tag in THINK_TAGS:
        if close_tag in content:
            head, _, tail = content.partition(close_tag)
            return head.strip(), tail.strip(), "closing_tag"

    return None, content.strip(), None


def response_meta(response):
    """応答そのものの素性。要求したモデル名と返ってきた実体名は別物。"""
    return {
        "response_model": getattr(response, "model", None),
        "system_fingerprint": getattr(response, "system_fingerprint", None),
        "finish_reason": getattr(response.choices[0], "finish_reason", None),
    }


def resolve_sample(design, repeat):
    """完全交差・均衡設計での (変種, seed)。仕様 第3節。

    標本 i = repeat − 1 に対し

        変種 = i // k          seed = seeds[i % k]        （k = 変種あたりの seed 数）

    **同一セル内では同じ seed 集合を全変種に交差させる。** 変種ごとに別の seed を
    振ると、変種効果と seed 効果がふたたび交絡する。設計を持たない条件では
    (None, None) を返し、呼び出し側が従来の規則に落ちる。
    """
    if not design:
        return None, None
    k = design["seeds_per_variant"]
    i = repeat - 1
    return i // k, design["seeds"][i % k]


def pick_variant(data, repeat):
    """条件が変種を持つなら、反復番号で1つ選ぶ。持たなければそのまま返す。

    計器v2（v4_distribution）で使う。外れコードのどの部分集合を書くかは一通りでは
    なく、固定すると特定の残候補集合の癖を測ることになる。**標本間で振るのが既定。**
    どの標本が何を見たかは、反復番号から決まるので後から辿れる。
    返り値は (投げる文書, 変種の番号)。変種を持たない条件では番号は None。
    """
    if isinstance(data, dict) and isinstance(data.get("variants"), list) and data["variants"]:
        index = (repeat - 1) % len(data["variants"])
        return data["variants"][index], index
    return data, None


def run_task(client, model, condition, data, task, max_attempts=None, repeat=1, prompts=None,
             sampling=None, variant=None, seed=None):
    """1タスクを1条件で1回走らせる。正答するか試行を使い切るまで繰り返す。

    ここでいう「試行（attempt）」は同じ会話の中でのリトライ。反復（repeat）は
    会話を捨てて最初からやり直す独立な標本で、呼び出し側が回す。
    """
    max_attempts = MAX_ATTEMPTS if max_attempts is None else max_attempts
    prompts = load_prompts(PROMPT_SET) if prompts is None else prompts
    if sampling is None:
        sampling = {"requested": sampling_params(), "used": sampling_params(), "dropped": {}}
    # 設計が変種と seed を決めているならそれに従う。無ければ従来の規則。
    if variant is None:
        payload, variant = pick_variant(data, repeat)
    else:
        payload = data["variants"][variant % len(data["variants"])]
    if seed is None:
        seed = seed_for_repeat(repeat)
    messages = [
        {
            "role": "user",
            "content": prompts["prompt"].format(
                data=json.dumps(payload, ensure_ascii=False, indent=2),
                query=task["query"],
            ),
        }
    ]
    truth = normalize_truth(task["ground_truth"])

    attempts = []
    thinking_chars = 0
    thinking_seen = False
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
            response = create_completion(client, model, messages, sampling, repeat, seed)
        except Exception as exc:  # 何が飛んでも、そこまでに消費したトークンは残す
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
            attempts.append({"attempt": attempt_no, "error": error})
            break

        thinking, answer, thinking_source = split_thinking(response.choices[0].message)
        meta = response_meta(response)
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

        if thinking is not None:
            thinking_seen = True
            thinking_chars += len(thinking)

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
                # 思考テキストそのもの。取れなければ null。
                "thinking": thinking,
                "thinking_chars": None if thinking is None else len(thinking),
                # どの経路で取り出したか。系統によって形が違うので残す。
                "thinking_source": thinking_source,
                # 思考のトークン数。サーバが usage で返したものが正。
                # 返らない場合は count_thinking.py が後から数えて埋める。
                "thinking_tokens": usage["reasoning"],
                "thinking_tokens_source": None if usage["reasoning"] is None else "server",
                # 生成上限に達して打ち切られたか。達しても集計からは外さない。
                "output_capped": meta["finish_reason"] == "length",
                **meta,
            }
        )

        if success:
            break

        messages.append({"role": "assistant", "content": answer or EMPTY_ANSWER_PLACEHOLDER})
        messages.append({"role": "user", "content": prompts["retry"]})

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
        # どの変種（外れコードの部分集合）を見たか。変種を持たない条件では null。
        "variant": variant,
        # この反復で実際に送った seed。サーバに拒まれて落ちていれば null。
        # 規則は fingerprint.settings.seed_rule にある。
        "seed": seed if "seed" in sampling["used"] else None,
        "status": status,
        # 最後の応答の素性。実体名が途中で変わった場合は attempt_log を見る。
        "response_model": attempts[-1].get("response_model") if attempts else None,
        "system_fingerprint": attempts[-1].get("system_fingerprint") if attempts else None,
        "finish_reason": attempts[-1].get("finish_reason") if attempts else None,
        # 思考が取れたか。取れていない（API経由など）場合は null で、0 と区別する。
        "thinking_chars": thinking_chars if thinking_seen else None,
        # 生成上限に達した試行の数。0 は「達しなかった」で、上限を送っていない
        # 場合との区別は fingerprint.settings.sampling_requested を見る。
        "output_capped_attempts": sum(1 for a in attempts if a.get("output_capped")),
        # どの経路で思考を取り出したか（試行をまたいで同じはず）。
        "thinking_source": next(
            (a["thinking_source"] for a in attempts if a.get("thinking_source")), None
        ),
        "error": error,
        # 測定の結果か、基盤の都合か。再開時に引き継ぐかどうかがこれで決まる。
        "error_class": classify_error(error),
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
    parser.add_argument("--suite", help="データとタスクの組（SUITE を上書き。suites/ 配下の名前）")
    parser.add_argument("--prompt", help="プロンプト一式（PROMPT を上書き。prompts.json のキー）")
    parser.add_argument(
        "--conditions",
        help="走らせるデータ条件をカンマ区切りで絞る（既定は組の全条件）",
    )
    parser.add_argument("--tasks", help="走らせるタスクIDをカンマ区切りで絞る（既定は全タスク）")
    parser.add_argument(
        "--show-trials",
        action="store_true",
        help="反復1回ごとの明細を表示する（既定は件数が多いと省略。JSONには常に入る）",
    )
    parser.add_argument("--no-save", action="store_true", help="results/ に書き出さない")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="同じ設定の途中経過があっても使わず、最初から回す",
    )
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

    # `or` で既定に落とすと 0 が黙って既定値に化ける。指定されたかどうかで見る。
    max_attempts = MAX_ATTEMPTS if args.max_attempts is None else args.max_attempts
    repeats = REPEATS if args.repeats is None else args.repeats
    if max_attempts < 1:
        raise SystemExit("--max-attempts / MAX_ATTEMPTS は1以上である必要があります")
    if repeats < 1:
        raise SystemExit("--repeats / REPEATS は1以上である必要があります")
    client = build_client(mock=args.mock)

    suite = args.suite or SUITE
    tasks, conditions, condition_spec = load_suite(suite)
    prompt_set = args.prompt or PROMPT_SET
    prompts = load_prompts(prompt_set)

    if args.conditions:
        wanted = [c.strip() for c in args.conditions.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in conditions]
        if unknown:
            raise SystemExit(
                f"条件 {', '.join(unknown)} は組 {suite!r} にありません。"
                f"あるのは: {', '.join(conditions)}"
            )
        conditions = {c: conditions[c] for c in wanted}
        condition_spec = [e for e in condition_spec if e["name"] in conditions]

    if args.tasks:
        wanted = [t.strip() for t in args.tasks.split(",") if t.strip()]
        known = {t["task_id"] for t in tasks}
        unknown = [t for t in wanted if t not in known]
        if unknown:
            raise SystemExit(
                f"タスク {', '.join(unknown)} は組 {suite!r} にありません。"
                f"あるのは: {', '.join(sorted(known))}"
            )
        tasks = [t for t in tasks if t["task_id"] in wanted]

    # 標本設計を持つ組では、セルごとに標本数が違う。総数はその和になる。
    designs = {c["name"]: c.get("design") for c in condition_spec}
    per_cell = [designs.get(name)["n"] if designs.get(name) else repeats
                for name in conditions]
    planned = len(models) * len(tasks) * sum(per_cell)
    cells = len(models) * len(conditions) * len(tasks)
    print(
        f"組 {suite} / プロンプト {prompt_set} / thinking {THINKING}: "
        f"{cells} セル / 計 {planned} 標本"
        + ("" if len(set(per_cell)) == 1 else "（セルごとに標本数が違う）")
    )

    # 結果ファイルだけを見て、どの入力で出たものか分かるようにする。
    # 指紋は突き合わせ用、inputs は中身そのもの（組は編集されるので、名前だけでは
    # 同じ入力だったことを保証できない）。ループの前に作るのは、途中経過の
    # 置き場所を指紋から決めるため。
    inputs = {"tasks": tasks, "conditions": conditions, "condition_spec": condition_spec}
    fingerprint = {
        "algorithm": f"sha256[:{FINGERPRINT_BITS}] of compact JSON",
        "suite": suite,
        "tasks": digest(tasks),
        "condition_spec": digest(condition_spec),
        "conditions": {name: digest(data) for name, data in conditions.items()},
        "inputs": digest(inputs),
        "prompt_set": prompt_set,
        "prompt": digest([prompts["prompt"], prompts["retry"]]),
        "models": models,
        "code": {
            "run_benchmark.py": file_digest(BASE_DIR / "run_benchmark.py"),
            "summarize.py": file_digest(BASE_DIR / "summarize.py"),
            "prompts.json": file_digest(PROMPTS_PATH),
        },
        "git": git_state(),
        "settings": {
            "max_attempts": max_attempts,
            "repeats": repeats,
            "request_timeout": REQUEST_TIMEOUT,
            "max_retries": MAX_RETRIES,
            "sampling_requested": sampling_params(),
            # sampling_requested の seed は repeat=1 の値。実際に送る値は
            # 反復ごとに違い、規則は seed_rule に、送った値は各試行の seed に入る。
            "seed_rule": SEED_RULE,
            # 中間推論を働かせたかどうか。on と off は別の測定として扱う。
            "thinking_mode": THINKING,
        },
        "sampling": digest(sampling_params()),
        "thinking_mode": THINKING,
    }

    # 途中経過。1試行ごとに書き足すので、落ちてもそこまでは残る。
    # 保存しない指定のときは何も書かない。
    checkpoint = None if args.no_save else partial_path(fingerprint)
    resumed = []
    if checkpoint is not None and not args.no_resume:
        resumed = load_partial(checkpoint, fingerprint)
        if resumed:
            print(f"途中経過 {checkpoint.name} から {len(resumed)} 件を引き継ぐ")
    by_key = {trial_key(r): r for r in resumed}
    reused = 0

    started_at = datetime.now(timezone.utc)
    results = []
    # サンプリング設定はモデルごとに持つ。受け付けないパラメータがあれば
    # そのモデルの分だけ落ちる。何が落ちたかはランごとに残す。
    sampling_by_model = {
        m: {"requested": sampling_params(), "used": sampling_params(), "dropped": {}}
        for m in models
    }
    # セルが標本設計を持つなら、標本数も変種も seed もそこから決まる（計器v2）。
    # 持たない組では従来どおり、全セル共通の反復数と seed 規則を使う。
    spec_by_name = {c["name"]: c for c in condition_spec}
    for model in models:
        for condition, data in conditions.items():
            design = (spec_by_name.get(condition) or {}).get("design")
            cell_repeats = design["n"] if design else repeats
            for task in tasks:
                for repeat in range(1, cell_repeats + 1):
                    key = (model, condition, task["task_id"], repeat)
                    if key in by_key:
                        results.append(by_key[key])
                        reused += 1
                        continue
                    variant, seed = resolve_sample(design, repeat)
                    print(
                        f"running: {model} / {condition} / {task['task_id']}"
                        f" [{repeat}/{cell_repeats}]"
                        + (f" 変種{variant} seed{seed}" if design else "")
                    )
                    result = run_task(
                        client, model, condition, data, task, max_attempts, repeat, prompts,
                        sampling_by_model[model], variant=variant, seed=seed,
                    )
                    if result["status"] == "error":
                        print(f"  error: {result['error']}")
                    elif not result["tokens_measured"]:
                        print("  warning: usage が返らないためトークンを計測できていません")
                    if checkpoint is not None:
                        append_partial(checkpoint, fingerprint, result)
                    results.append(result)

    if reused:
        print(f"（{reused} 件は途中経過から引き継いだもの。新しく回したのは "
              f"{len(results) - reused} 件）")

    print()
    if args.show_trials or len(results) <= TRIAL_TABLE_LIMIT:
        print_trial_table(results)
    else:
        print(
            f"反復ごとの明細 {len(results)} 件は省略した（--show-trials で表示）。"
            "JSONには常に入っている。"
        )

    finished_at = datetime.now(timezone.utc)
    run = {
        "run_at": started_at.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_sec": round((finished_at - started_at).total_seconds(), 1),
        "argv": sys.argv,
        # 途中経過から引き継いだ件数。0 なら一度で通したラン。
        "resumed_trials": reused,
        "environment": {
            "python": sys.version.split()[0],
            "openai_sdk": sdk_version(),
            "platform": sys.platform,
        },
        # 中間推論を働かせたか。off なら chat_template_kwargs で切っている。
        "thinking_mode": THINKING,
        # 実行経路。RUN_ROUTE は人が書くもので、空なら記録していないという意味。
        "route": {
            "note": RUN_ROUTE,
            "base_url": "mock://" if args.mock else BASE_URL,
            "local_server": (not args.mock) and (
                "localhost" in BASE_URL or "127.0.0.1" in BASE_URL
            ),
        },
        # 要求した設定と、モデルが実際に受け付けた設定。落ちたものは理由つき。
        "sampling": {
            m: {"requested": st["requested"], "used": st["used"], "dropped": st["dropped"]}
            for m, st in sampling_by_model.items()
        },
        "fingerprint": fingerprint,
        "inputs": inputs,
        "base_url": "mock://" if args.mock else BASE_URL,
        "mock": args.mock,
        "suite": suite,
        "prompt_set": prompt_set,
        # 投げた全文をそのまま残す。あとから何を投げたか分からない状態にしない。
        "prompt_text": {"prompt": prompts["prompt"], "retry": prompts["retry"]},
        "models": models,
        "max_attempts": max_attempts,
        "repeats": repeats,
        "conditions": list(conditions),
        # 各条件に何を置いたか。機械可読のまま残す。
        "condition_spec": condition_spec,
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
        # 完走して本体を書き出せたので、途中経過はもう要らない。
        if checkpoint is not None and checkpoint.is_file():
            checkpoint.unlink()
            print(f"途中経過を片付けた: {checkpoint.name}")

    return run


if __name__ == "__main__":
    main()
