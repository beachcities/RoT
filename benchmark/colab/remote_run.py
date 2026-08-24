# -*- coding: utf-8 -*-
"""Colab の VM 側で1区間ぶんだけ走らせる。

`drive_cli_run.py` が session ごとに呼ぶ。CLI 経路のセッションは 61.5 分で切れるので、
**期限より手前で自分から止まり、そこまでの途中経過を残す**。次の区間は、その途中経過を
持ち込んで続きから回す。

引数は環境変数で渡す:

    ROT_DEADLINE_SEC  この秒数を過ぎたら run_benchmark を終わらせる
    ROT_MODEL         モデルID
    ROT_THINKING      on / off
    ROT_TASKS, ROT_SUITE, ROT_REPEATS, ROT_MAX_ATTEMPTS, ROT_MAX_OUTPUT_TOKENS
    ROT_MAX_MODEL_LEN vLLM の --max-model-len（生成上限より大きくすること）
    ROT_USE_LOCAL     1 なら /content/local を clone の上に被せる（未 push のコードを試すとき）
    ROT_ROUTE         実行経路の覚え書き（結果に残る）

終了時に `/content/status.json` を書く。`done` が真なら完走している。
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = "https://github.com/beachcities/RoT.git"
BENCH = "/content/RoT/benchmark"
PORT = "8000"


def env(name, default=""):
    return os.environ.get(name, default)


def log(*a):
    print(*a, flush=True)


def overlay_local():
    """手元から持ち込んだファイルを clone の上に被せる。

    **push していないコードを試すための逃げ道。** 被せた結果は clone との差分として
    残るので、`git status` が dirty を返し、指紋にもそう記録される。
    どのコードで回したかを偽らずに済む。
    """
    src = "/content/local"
    if env("ROT_USE_LOCAL") != "1" or not os.path.isdir(src):
        return 0
    n = 0
    for root, _, files in os.walk(src):
        for name in files:
            rel = os.path.relpath(os.path.join(root, name), src)
            dst = os.path.join(BENCH, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(os.path.join(root, name), "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)
            n += 1
    log(f"手元のファイルを {n} 件被せた（clone との差分になる）")
    return n


def prepare():
    if not os.path.isdir("/content/RoT"):
        subprocess.run(["git", "clone", "--depth", "1", REPO, "/content/RoT"], check=True)
    commit = subprocess.run(["git", "-C", "/content/RoT", "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    log("commit:", commit)
    overlay_local()
    # Colab のイメージは torch と torchaudio の CUDA 版が食い違っており、
    # vLLM の import 経路で落ちる。テキスト推論に torchaudio は要らない。
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchaudio"])
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openai", "python-dotenv"])
    try:
        import vllm  # noqa: F401
    except ImportError:
        log("vllm を入れる")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "vllm"], check=True)
    with open(BENCH + "/.env", "w") as f:
        f.write("API_KEY=dummy" + chr(10) + f"BASE_URL=http://127.0.0.1:{PORT}/v1" + chr(10))
    return commit


def restore_partial():
    """前の区間から持ち込んだ途中経過を results/partial/ に戻す。"""
    src = "/content/carry"
    if not os.path.isdir(src):
        return 0
    dst = BENCH + "/results/partial"
    os.makedirs(dst, exist_ok=True)
    n = 0
    for name in os.listdir(src):
        if name.endswith(".jsonl"):
            with open(os.path.join(src, name), encoding="utf-8") as f:
                data = f.read()
            with open(os.path.join(dst, name), "w", encoding="utf-8") as f:
                f.write(data)
            n += len(data.strip().split(chr(10))) - 1     # 見出し行を除く
    log(f"持ち込んだ途中経過: {n} 試行")
    return n


def serve(model, max_model_len):
    """vLLM を立ち上げて READY まで待つ。パーサは付けない。

    パーサ有りだと reasoning_content が空で返り、思考テキストが失われる（実測）。
    付けなければ </think> が本文に残り、ランナー側が切り出せる。
    """
    log(f"vllm serve {model} --max-model-len {max_model_len}")
    logfile = open("/content/vllm.log", "w")
    proc = subprocess.Popen(
        ["vllm", "serve", model, "--port", PORT, "--max-model-len", str(max_model_len),
         "--gpu-memory-utilization", "0.90"],
        stdout=logfile, stderr=subprocess.STDOUT)
    for i in range(150):
        time.sleep(10)
        if proc.poll() is not None:
            log("サーバが落ちた")
            log(open("/content/vllm.log").read()[-2000:])
            return None
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=3)
            log(f"READY after {(i + 1) * 10}s")
            return proc
        except Exception:
            pass
    log("読み込みが終わらない")
    log(open("/content/vllm.log").read()[-1500:])
    return None


def gpu_name():
    return subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout.strip()


def main():
    started = time.time()
    deadline = float(env("ROT_DEADLINE_SEC", "2700"))
    model = env("ROT_MODEL", "Qwen/Qwen3.5-9B")

    # 文脈長が生成上限以下だと、プロンプトを足した時点で必ず超えて 400 になる。
    # 実測でこれを踏み、20実行すべてがエラーになった。先に弾く。
    max_model_len = int(env("ROT_MAX_MODEL_LEN", "65536"))
    max_output = int(env("ROT_MAX_OUTPUT_TOKENS", "32768"))
    if max_model_len <= max_output:
        raise SystemExit(
            f"--max-model-len ({max_model_len}) が生成上限 ({max_output}) 以下です。"
            "プロンプトを足した時点で必ず超えるので、全試行が 400 になります。"
        )
    commit = prepare()
    carried = restore_partial()

    server = serve(model, max_model_len)
    status = {"done": False, "carried": carried, "commit": commit, "model": model,
              "gpu": gpu_name(), "result_file": None, "reason": None}
    if server is None:
        status["reason"] = "サーバが立ち上がらなかった"
        json.dump(status, open("/content/status.json", "w"), ensure_ascii=False)
        return

    child_env = dict(
        os.environ, PYTHONIOENCODING="utf-8",
        SUITE=env("ROT_SUITE", "v3_levels"), PROMPT="p1_baseline",
        REPEATS=env("ROT_REPEATS", "1"), MAX_ATTEMPTS=env("ROT_MAX_ATTEMPTS", "10"),
        MAX_OUTPUT_TOKENS=env("ROT_MAX_OUTPUT_TOKENS", "32768"),
        THINKING=env("ROT_THINKING", "on"),
        TEMPERATURE="1.0", TOP_P="1.0", SEED="20260820",
        REQUEST_TIMEOUT="1800", MAX_RETRIES="2",
        RUN_ROUTE=(env("ROT_ROUTE", "Colab CLI 経路 / colab/remote_run.py")
                   + f" / GPU: {status['gpu']} / vllm serve --max-model-len "
                   + str(max_model_len)
                   + " --gpu-memory-utilization 0.90（reasoning-parser なし）"
                   + (" / 手元のコードを被せて実行" if env("ROT_USE_LOCAL") == "1" else "")),
    )
    cmd = [sys.executable, "-u", "run_benchmark.py", "--models", model,
           "--tasks", env("ROT_TASKS", "task_04,task_06")]
    if env("ROT_CONDITIONS"):
        cmd += ["--conditions", env("ROT_CONDITIONS")]
    log("走らせる:", " ".join(cmd), "/ THINKING=" + child_env["THINKING"])

    remaining = deadline - (time.time() - started)
    proc = subprocess.Popen(cmd, cwd=BENCH, env=child_env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in proc.stdout:
            log(line.rstrip())
            if time.time() - started > deadline:
                log(f"期限 {deadline:.0f}s を過ぎたので、この区間はここまでにする")
                proc.terminate()
                break
        proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        proc.kill()

    status["done"] = proc.returncode == 0
    status["returncode"] = proc.returncode
    status["elapsed_sec"] = round(time.time() - started, 1)
    if status["done"]:
        import glob
        files = sorted(glob.glob(BENCH + "/results/run_*.json"))
        status["result_file"] = files[-1] if files else None
        # 完走しても、全試行がエラーなら測定として成立していない。数えて残す。
        if status["result_file"]:
            with open(status["result_file"], encoding="utf-8") as f:
                done_run = json.load(f)
            rows = done_run["results"]
            status["trials"] = len(rows)
            status["errors"] = sum(1 for r in rows if r["status"] != "ok")
            status["thinking_mode"] = done_run.get("thinking_mode")
    json.dump(status, open("/content/status.json", "w"), ensure_ascii=False)
    log("status:", json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
