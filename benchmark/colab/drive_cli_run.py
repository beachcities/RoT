# -*- coding: utf-8 -*-
"""Colab CLI 経路で、セッションの上限をまたいで走らせ続ける。

    python colab/drive_cli_run.py --thinking on
    python colab/drive_cli_run.py --thinking off --model Qwen/Qwen3.5-9B

CLI 経路のセッションは **61.5 分で切れる**。この測定は1本で2〜5時間かかりうるので、
1セッションには収まらない。そこで区間に分けて回す。

    セッションを作る → 前の区間の途中経過を持ち込む → 期限手前まで走る
    → 途中経過を手元に降ろす → セッションを止める → 完走するまで繰り返す

途中経過は1試行ごとに書かれているので、区間の切れ目で失うのは走っている最中の
1試行だけ。指紋が一致しない途中経過は `run_benchmark.py` 側が受け付けないので、
設定を変えたまま続きから回してしまうことはない。

## 自動ではあるが、無人ではない

**この駆動スクリプトは手元の機械で動き続ける必要がある。** 手元が眠れば止まる。
Colab のブラウザ経路（上限なし）も、タブを開いたままにする必要がある点は同じで、
**どちらも「機械を起こしたまま放っておく」以上のことはできない**。
止まっても途中経過は残るので、再開すれば続きから走る。

## 区間あたりの目安

セッションを作り直すたびに、依存の導入とモデルの読み込みで 5〜10 分かかる。
既定では45分を作業に充てる（残りを立ち上げに使う）。1区間あたりの実効はおよそ 45 分。
"""

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CARRY_DIR = BASE_DIR / "results" / "partial"
REMOTE_SCRIPT = Path(__file__).resolve().parent / "remote_run.py"


def wsl_path(path):
    """Windows のパスを WSL から見える形に直す。colab CLI は WSL の中で動く。"""
    p = str(Path(path).resolve()).replace("\\", "/")
    if len(p) > 1 and p[1] == ":":
        p = f"/mnt/{p[0].lower()}{p[2:]}"
    return p


def colab(*args, timeout=1800, check=True):
    cmd = ["colab", *args]
    print(f"  $ {' '.join(cmd)}", flush=True)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                         encoding="utf-8", errors="replace", shell=True)
    if out.stdout:
        print("    " + out.stdout.strip().replace("\n", "\n    "), flush=True)
    if check and out.returncode != 0:
        print("    " + (out.stderr or "").strip()[:800], flush=True)
        raise SystemExit(f"colab {args[0]} が失敗した")
    return out


def ensure_dirs(session):
    """アップロード先のディレクトリを先に作る。

    `colab upload` はネストした宛先を作れず、無いと 500 を返す（実測）。
    `/content/carry` は区間2以降で必ず使うので、毎回作っておく。
    """
    lines = [
        "import os",
        "for d in ('/content/carry', '/content/local'):",
        "    os.makedirs(d, exist_ok=True)",
        "print('ディレクトリを用意した')",
    ]
    script = BASE_DIR / "results" / ".mkdirs.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    colab("exec", "-s", session, "--timeout", "120", "-f", wsl_path(script), timeout=300)
    script.unlink(missing_ok=True)


def carry_files():
    if not CARRY_DIR.is_dir():
        return []
    return sorted(CARRY_DIR.glob("partial_*.jsonl"))


def run_segment(session, args, index):
    """1区間ぶん。完走したら結果ファイルのパスを返す。"""
    print(f"\n=== 区間 {index} ===", flush=True)
    colab("new", "-s", session, "--gpu", args.gpu, timeout=900)
    try:
        ensure_dirs(session)
        for f in carry_files():
            colab("upload", "-s", session, wsl_path(f), f"/content/carry/{f.name}",
                  timeout=600)
        colab("upload", "-s", session, wsl_path(REMOTE_SCRIPT), "/content/remote_run.py",
              timeout=600)
        if args.use_local:
            # clone は origin/main を取ってくるので、push していない変更は入らない。
            # 実測でこれを踏み、thinking を切ったつもりが切れていなかった。
            for name in ("run_benchmark.py", "summarize.py", "mock_client.py",
                         "prompts.json", "count_thinking.py"):
                colab("upload", "-s", session, wsl_path(BASE_DIR / name),
                      f"/content/local/{name}", timeout=600)

        setup = (
            "import os, runpy\n"
            f"os.environ.update({{"
            f"'ROT_DEADLINE_SEC': '{args.work_seconds}',"
            f"'ROT_MODEL': '{args.model}',"
            f"'ROT_THINKING': '{args.thinking}',"
            f"'ROT_TASKS': '{args.tasks}',"
            f"'ROT_SUITE': '{args.suite}',"
            f"'ROT_REPEATS': '{args.repeats}',"
            f"'ROT_MAX_ATTEMPTS': '{args.max_attempts}',"
            f"'ROT_MAX_OUTPUT_TOKENS': '{args.max_output_tokens}',"
            f"'ROT_MAX_MODEL_LEN': '{args.max_model_len}',"
            f"'ROT_USE_LOCAL': '{'1' if args.use_local else '0'}',"
            f"'ROT_CONDITIONS': '{args.conditions}',"
            f"'ROT_COMMIT': '{args.commit}',"
            f"'ROT_ROUTE': 'Colab CLI 経路 / colab/drive_cli_run.py'}})\n"
            "runpy.run_path('/content/remote_run.py', run_name='__main__')\n"
        )
        script = BASE_DIR / "results" / f".segment_{index}.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(setup, encoding="utf-8")
        colab("exec", "-s", session, "--timeout", str(args.work_seconds + 1200),
              "-f", wsl_path(script), timeout=args.work_seconds + 1500, check=False)
        script.unlink(missing_ok=True)

        status_local = BASE_DIR / "results" / f".status_{index}.json"
        colab("download", "-s", session, "/content/status.json", wsl_path(status_local),
              timeout=600, check=False)
        status = {}
        if status_local.is_file():
            status = json.loads(status_local.read_text(encoding="utf-8"))
            status_local.unlink()
        print(f"  status: {json.dumps(status, ensure_ascii=False)}", flush=True)

        if status.get("errors"):
            print(f"  ** {status['errors']}/{status['trials']} 試行がエラー。"
                  "測定として成立していない可能性がある **", flush=True)
        if status.get("done") and status.get("result_file"):
            out = BASE_DIR / "results" / Path(status["result_file"]).name
            colab("download", "-s", session, status["result_file"], wsl_path(out), timeout=900)
            return out

        # 完走していないので、途中経過を降ろして次の区間へ
        listing = colab("ls", "-s", session, "/content/RoT/benchmark/results/partial",
                        timeout=600, check=False)
        CARRY_DIR.mkdir(parents=True, exist_ok=True)
        for name in listing.stdout.split():
            if name.endswith(".jsonl"):
                colab("download", "-s", session,
                      f"/content/RoT/benchmark/results/partial/{name}",
                      wsl_path(CARRY_DIR / name), timeout=900, check=False)
        return None
    finally:
        colab("stop", "-s", session, timeout=600, check=False)


def main():
    parser = argparse.ArgumentParser(description="CLI 経路で区間に分けて走らせる")
    parser.add_argument("--thinking", choices=("on", "off"), default="on")
    parser.add_argument("--model", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--tasks", default="task_04,task_06")
    parser.add_argument("--suite", default="v3_levels")
    parser.add_argument("--commit", default="",
                        help="clone をこのコミットに固定する。区間をまたぐ間に "
                             "origin/main が進んでも途中経過が弾かれない")
    parser.add_argument("--conditions", default="",
                        help="水準を絞る（事前確認に使う。既定は組の全水準）")
    parser.add_argument("--repeats", default="1")
    parser.add_argument("--max-attempts", default="10")
    parser.add_argument("--max-output-tokens", default="32768")
    parser.add_argument("--max-model-len", default="65536",
                        help="生成上限より大きくすること。以下だと全試行が 400 になる")
    parser.add_argument("--use-local", action="store_true",
                        help="push していない手元のコードを clone の上に被せて走らせる")
    parser.add_argument("--gpu", default="A100")
    parser.add_argument("--work-seconds", type=int, default=2700,
                        help="1区間で走らせる秒数。立ち上げの時間を差し引いて決める")
    parser.add_argument("--max-segments", type=int, default=12,
                        help="この回数で打ち切る（暴走の歯止め）")
    parser.add_argument("--session", default="rot-drive")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    print(f"モデル {args.model} / thinking {args.thinking} / {args.tasks}")
    print(f"1区間 {args.work_seconds}s、最大 {args.max_segments} 区間")
    if args.use_local:
        print("手元のコードを被せて走らせる（clone との差分になり、指紋は dirty になる）")
    if int(args.max_model_len) <= int(args.max_output_tokens):
        raise SystemExit(
            f"--max-model-len ({args.max_model_len}) が --max-output-tokens "
            f"({args.max_output_tokens}) 以下です。全試行が 400 になります。")
    if carry_files():
        print(f"引き継ぐ途中経過: {[f.name for f in carry_files()]}")

    started = time.time()
    for index in range(1, args.max_segments + 1):
        result = run_segment(f"{args.session}-{index}", args, index)
        if result:
            print(f"\n完走した: {result}  （合計 {(time.time() - started) / 60:.0f} 分、"
                  f"{index} 区間）")
            return
    print(f"\n{args.max_segments} 区間で打ち切った。途中経過は {CARRY_DIR} にある。"
          "同じ引数でもう一度走らせれば続きから回る。")


if __name__ == "__main__":
    main()
