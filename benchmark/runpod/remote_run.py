# -*- coding: utf-8 -*-
"""RunPod の Pod 上で走らせる。setup.sh から呼ばれる。

Colab 経路（`colab/remote_run.py`）との違いは、**セッションの上限が無いので
区間に分ける必要がない**ことだけ。測っているものも、途中経過の残し方も同じで、
指紋が合わない途中経過はランナー側が受け付けない。

引数は環境変数で受け取る。`colab/remote_run.py` と同じ名前を使う。

    ROT_MODEL, ROT_THINKING, ROT_TASKS, ROT_SUITE, ROT_CONDITIONS,
    ROT_REPEATS, ROT_MAX_ATTEMPTS, ROT_MAX_OUTPUT_TOKENS, ROT_MAX_MODEL_LEN,
    ROT_DEADLINE_SEC   この秒数で run_benchmark を終わらせる（課金の歯止め）
    ROT_ROUTE          経路の覚え書き（結果に残る）

終了時に `/workspace/out/status.json` を書く。結果と途中経過は
`/workspace/out/` に置く。**Pod は使い捨てなので、取りに来られる場所に必ず出す。**
"""

import glob
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

BENCH = "/workspace/RoT/benchmark"
OUT = "/workspace/out"
PORT = "8000"


def tag(model):
    """モデル名をファイル名に使える形にする。1 Pod で複数モデルを回すと、
    status や timings が上書きし合うため。"""
    return model.replace("/", "_").replace(":", "_")


def env(name, default=""):
    return os.environ.get(name, default)


def log(*a):
    print(*a, flush=True)


def restore_partial():
    """持ち込んだ途中経過を results/partial/ に戻す。再開はここから始まる。"""
    src = "/workspace/carry"
    if not os.path.isdir(src):
        return 0
    dst = os.path.join(BENCH, "results", "partial")
    os.makedirs(dst, exist_ok=True)
    n = 0
    for name in os.listdir(src):
        if name.endswith(".jsonl"):
            shutil.copy(os.path.join(src, name), os.path.join(dst, name))
            with open(os.path.join(src, name), encoding="utf-8") as f:
                n += len(f.read().strip().split(chr(10))) - 1      # 見出し行を除く
    log(f"持ち込んだ途中経過: {n} 試行")
    return n


def evacuate():
    """途中経過を取りに来られる場所へ写す。**落ちる前提で、こまめに呼ぶ。**"""
    src = os.path.join(BENCH, "results", "partial")
    if not os.path.isdir(src):
        return 0
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for path in glob.glob(os.path.join(src, "partial_*.jsonl")):
        shutil.copy(path, os.path.join(OUT, os.path.basename(path)))
        n += 1
    return n


def serve(model, max_model_len):
    """vLLM を立ち上げて READY まで待つ。パーサは付けない。

    パーサ有りだと reasoning_content が空で返り、思考テキストが失われる（実測）。
    付けなければ </think> が本文に残り、ランナー側が切り出せる。
    """
    # **前のモデルのサーバが生きたままだと、口が開いているので READY と判定して
    # しまう。** 実測: 1つの Pod で2モデル目を立てたとき、健全性の確認が前段の
    # サーバに当たり、2モデル目の全試行が 404 になった。先に必ず落とす。
    subprocess.run(["pkill", "-f", "vllm.entrypoints.openai.api_server"],
                   capture_output=True)
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models", timeout=2)
            time.sleep(2)
        except Exception:
            break
    else:
        log("前のサーバが落ちない")
        return None, None

    log(f"vllm serve {model} --max-model-len {max_model_len}")
    logfile = open(f"/workspace/out/vllm_{tag(model)}.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "vllm.entrypoints.openai.api_server",
         "--model", model, "--port", PORT, "--max-model-len", str(max_model_len),
         "--gpu-memory-utilization", "0.90"],
        stdout=logfile, stderr=subprocess.STDOUT)
    started = time.time()
    for _ in range(180):
        time.sleep(10)
        if proc.poll() is not None:
            log("サーバが落ちた")
            log(open(f"/workspace/out/vllm_{tag(model)}.log").read()[-2000:])
            return None, None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/v1/models",
                                        timeout=3) as resp:
                served = [m["id"] for m in json.load(resp).get("data", [])]
            if model not in served:
                # 別のモデルを出しているサーバに当たっている。測定として成立しない。
                log(f"** 口は開いているが {served} を出している（欲しいのは {model}）**")
                proc.terminate()
                return None, None
            wait = round(time.time() - started, 1)
            log(f"READY after {wait}s / 出しているモデル: {served}")
            return proc, wait
        except Exception:
            pass
    log("読み込みが終わらない")
    log(open(f"/workspace/out/vllm_{tag(model)}.log").read()[-1500:])
    return None, None


def gpu_name():
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                          "--format=csv,noheader"], capture_output=True, text=True)
    return out.stdout.strip()


def main():
    started = time.time()
    deadline = float(env("ROT_DEADLINE_SEC", "3600"))
    model = env("ROT_MODEL", "Qwen/Qwen3.5-9B")

    # 文脈長が生成上限以下だと、プロンプトを足した時点で必ず超えて 400 になる。
    # Colab で実測して20実行すべてを失っている。先に弾く。
    max_model_len = int(env("ROT_MAX_MODEL_LEN", "65536"))
    max_output = int(env("ROT_MAX_OUTPUT_TOKENS", "32768"))
    if max_model_len <= max_output:
        raise SystemExit(
            f"--max-model-len ({max_model_len}) が生成上限 ({max_output}) 以下です。"
            "プロンプトを足した時点で必ず超えるので、全試行が 400 になります。")

    os.makedirs(OUT, exist_ok=True)
    timings = {}
    stamp = f"{OUT}/timings_{tag(model)}.json"
    if os.path.exists(stamp):
        timings = json.load(open(stamp, encoding="utf-8"))

    commit = subprocess.run(["git", "-C", "/workspace/RoT", "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    carried = restore_partial()
    with open(os.path.join(BENCH, ".env"), "w") as f:
        f.write("API_KEY=dummy" + chr(10) + f"BASE_URL=http://127.0.0.1:{PORT}/v1" + chr(10))

    server, ready_sec = serve(model, max_model_len)
    status = {"done": False, "carried": carried, "commit": commit, "model": model,
              "gpu": gpu_name(), "result_file": None, "reason": None, "timings": timings}
    timings["serve_ready_sec"] = ready_sec
    if server is None:
        status["reason"] = "サーバが立ち上がらなかった"
        json.dump(status, open(f"{OUT}/status_{tag(model)}.json", "w"), ensure_ascii=False)
        return

    child = dict(
        os.environ, PYTHONIOENCODING="utf-8",
        SUITE=env("ROT_SUITE", "v3_levels"), PROMPT="p1_baseline",
        REPEATS=env("ROT_REPEATS", "5"), MAX_ATTEMPTS=env("ROT_MAX_ATTEMPTS", "10"),
        MAX_OUTPUT_TOKENS=env("ROT_MAX_OUTPUT_TOKENS", "32768"),
        THINKING=env("ROT_THINKING", "on"),
        TEMPERATURE="1.0", TOP_P="1.0", SEED="20260820",
        REQUEST_TIMEOUT="1800", MAX_RETRIES="2",
        RUN_ROUTE=(env("ROT_ROUTE", "RunPod 経路 / runpod/remote_run.py")
                   + f" / GPU: {status['gpu']} / vllm --max-model-len {max_model_len}"
                   + " --gpu-memory-utilization 0.90（reasoning-parser なし）"),
    )
    cmd = [sys.executable, "-u", "run_benchmark.py", "--models", model,
           "--tasks", env("ROT_TASKS", "task_04,task_06")]
    if env("ROT_CONDITIONS"):
        cmd += ["--conditions", env("ROT_CONDITIONS")]
    log("走らせる:", " ".join(cmd), "/ THINKING=" + child["THINKING"],
        "/ REPEATS=" + child["REPEATS"])

    run_started = time.time()
    # 落ちた状態を作るための、意図的な打ち切り。煙試験の再開試験で使う。
    stop_after = int(env("ROT_STOP_AFTER_TRIALS", "0") or 0)
    trials_seen = 0
    stopped_early = False
    proc = subprocess.Popen(cmd, cwd=BENCH, env=child,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for line in proc.stdout:
            log(line.rstrip())
            # 1試行終わるたびに退避する。Pod が消えても、ここまでは残る。
            if line.startswith("running:"):
                trials_seen += 1
                evacuate()
                if stop_after and trials_seen > stop_after:
                    log(f"ROT_STOP_AFTER_TRIALS={stop_after} に達したので、"
                        "途中経過を残して意図的に止める")
                    proc.terminate()
                    stopped_early = True
                    break
            if time.time() - started > deadline:
                log(f"期限 {deadline:.0f}s を過ぎたので止める")
                proc.terminate()
                break
        proc.wait(timeout=180)
    except subprocess.TimeoutExpired:
        proc.kill()
    timings["run_sec"] = round(time.time() - run_started, 1)

    status["stopped_early"] = stopped_early
    status["trials_started"] = trials_seen
    status["done"] = proc.returncode == 0 and not stopped_early
    status["returncode"] = proc.returncode
    status["elapsed_sec"] = round(time.time() - started, 1)
    status["evacuated"] = evacuate()
    if status["done"]:
        files = sorted(glob.glob(os.path.join(BENCH, "results", "run_*.json")))
        if files:
            shutil.copy(files[-1], os.path.join(OUT, os.path.basename(files[-1])))
            status["result_file"] = os.path.basename(files[-1])
            run = json.load(open(files[-1], encoding="utf-8"))
            rows = run["results"]
            status["trials"] = len(rows)
            status["errors"] = sum(1 for r in rows if r["status"] != "ok")
            status["thinking_mode"] = run.get("thinking_mode")
            status["seeds"] = sorted({r.get("seed") for r in rows})
    status["timings"] = timings
    json.dump(status, open(f"{OUT}/status_{tag(model)}.json", "w"), ensure_ascii=False)
    log("status:", json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    main()
