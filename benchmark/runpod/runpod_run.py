# -*- coding: utf-8 -*-
"""RunPod で1本走らせる外殻。**WSL 側（runpodctl と ssh のある側）で動かす。**

    python3 runpod/runpod_run.py --dry-run
    python3 runpod/runpod_run.py --model Qwen/Qwen3.5-9B --thinking on --repeats 5

Colab CLI 経路との違いは、セッションの上限が無いので区間に分けなくてよいこと。
代わりに**課金が続く**ので、止めることに責任を持つ。

## 止め方（二重にする）

1. `--terminate-after` を Pod 作成時に渡す。手元が落ちても Pod は自分で消える。
   日時指定なので、`--max-usd` から算出した秒数に余裕を足した時刻を渡す。
2. 手元では try/finally で必ず `pod delete` する。
3. **取り残しの判定は `runpodctl pod list` が空であること。** 消したつもりは
   証拠にならない。最後に必ず確かめて、空でなければ声を上げる。

## 家訓

* network volume は作らない（`--network-volume-id` は使わない）。
* Pod は使い捨て。結果は毎回 `--out` に降ろす。Pod 上に置いたままにしない。
* 秘密は env で渡し、ログに出さない。このスクリプトは鍵の値を印字しない。
"""

import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
KEY_PATH = Path.home() / ".secrets" / "runpod_api_key"
GPU_ID = "NVIDIA A100-SXM4-80GB"
# 既定のイメージ。**煙試験と本走行で同じものを使う。** 変えると所要が変わり、
# 煙試験で測った見積りがそのまま使えなくなる。
IMAGE = "runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404"
RATES = {"COMMUNITY": 1.39, "SECURE": 1.59}     # $/h、2026-08-25 に実測した値

SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR", "-o", "ServerAliveInterval=30"]


def log(*a):
    print(*a, flush=True)


def api_env():
    """鍵を env に載せる。**値は読むだけで、印字も記録もしない。**"""
    if not KEY_PATH.is_file():
        raise SystemExit(f"鍵が見つかりません: {KEY_PATH}")
    env = dict(os.environ)
    env["RUNPOD_API_KEY"] = KEY_PATH.read_text().strip()
    return env


def rp(*args, check=True, timeout=600):
    cmd = ["runpodctl", *args]
    log(f"  $ runpodctl {' '.join(args)}")
    out = subprocess.run(cmd, capture_output=True, text=True, env=api_env(),
                         timeout=timeout)
    if check and out.returncode != 0:
        log("    " + (out.stderr or out.stdout).strip()[:600])
        raise SystemExit(f"runpodctl {args[0]} が失敗した")
    return out.stdout.strip()


def pods():
    raw = rp("pod", "list", "-o", "json", check=False)
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("pods", [])
    return data or []


def create(args, seconds):
    """Pod を作る。自動終了の時刻を先に決めてから渡す。

    **在庫は出たり消えたりする。** 実測: 在庫 Low と表示されていても
    「no longer any instances available」で断られる。GPU を掴む前なので
    断られている間は課金されない。掴めるまで淡々と待つ。
    """
    for attempt in range(1, args.create_retries + 1):
        # 期限は掴めた時刻から数える。待っている間に前へずれないよう毎回引き直す。
        until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
            seconds=seconds + args.terminate_margin)
        stamp = until.strftime("%Y-%m-%dT%H:%M:%SZ")
        out = subprocess.run(
            ["runpodctl", "pod", "create", "--name", args.name, "--image", args.image,
             "--gpu-id", GPU_ID, "--cloud-type", args.cloud,
             "--container-disk-in-gb", str(args.disk),
             "--volume-in-gb", str(args.volume),
             "--ports", "22/tcp", "--terminate-after", stamp, "-o", "json"],
            capture_output=True, text=True, env=api_env(), timeout=600)
        text = (out.stdout or "") + (out.stderr or "")
        if out.returncode == 0 and "error" not in text[:20]:
            try:
                data = json.loads(out.stdout)
            except json.JSONDecodeError:
                data = {}
            pod = data.get("pod", data) if isinstance(data, dict) else data
            pod_id = pod.get("id") or pod.get("podId")
            if pod_id:
                log(f"自動終了を {stamp} に置いた"
                    f"（{(seconds + args.terminate_margin) / 60:.0f} 分後）")
                return pod_id
        short = text.strip().replace(chr(10), " ")[:160]
        log(f"  [{attempt}/{args.create_retries}] 取れない: {short}")
        if attempt < args.create_retries:
            time.sleep(args.create_wait)
    raise SystemExit(f"{args.create_retries} 回試して Pod を取れなかった")


def ssh_info(pod_id, wait_sec):
    """SSH の口が開くまで待つ。落ちてくるのは host と port。"""
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        raw = rp("ssh", "info", pod_id, "-o", "json", check=False)
        try:
            info = json.loads(raw or "{}")
        except json.JSONDecodeError:
            info = {}
        if isinstance(info, dict) and "connections" in info and info["connections"]:
            info = info["connections"][0]
        host = info.get("host") or info.get("ip") or info.get("publicIp")
        port = info.get("port") or info.get("sshPort") or info.get("publicPort")
        user = info.get("user") or "root"
        if host and port:
            log(f"  ssh {user}@{host} -p {port}")
            return user, host, int(port)
        time.sleep(15)
    raise SystemExit("SSH の口が開かない")


def wait_ssh(user, host, port, wait_sec):
    deadline = time.time() + wait_sec
    while time.time() < deadline:
        out = subprocess.run(["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}",
                              "echo ok"], capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and "ok" in out.stdout:
            return True
        time.sleep(15)
    return False


def scp_up(user, host, port, local, remote):
    subprocess.run(["scp", *SSH_OPTS, "-P", str(port), str(local),
                    f"{user}@{host}:{remote}"], check=True, timeout=600)


def scp_down(user, host, port, remote, local):
    out = subprocess.run(["scp", *SSH_OPTS, "-P", str(port), "-r",
                          f"{user}@{host}:{remote}", str(local)],
                         capture_output=True, text=True, timeout=1800)
    return out.returncode == 0


def run_remote(user, host, port, env_vars, logfile, timeout):
    """setup.sh を走らせ、出力をそのまま手元にも落とす。"""
    prefix = " ".join(f"{k}={shlex.quote(str(v))}" for k, v in env_vars.items())
    cmd = ["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}",
           f"{prefix} bash /workspace/setup.sh"]
    with open(logfile, "w", encoding="utf-8") as f:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        started = time.time()
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            f.write(line)
            if time.time() - started > timeout:
                proc.terminate()
                f.write("（手元の期限で打ち切った）\n")
                break
        try:
            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
    return proc.returncode


def teardown(pod_id):
    """必ず消す。判定の権威は pod list に**自分の Pod が居ないこと**。

    全体が空であることを条件にすると、並走しているもう一方のレーンを
    取り残しと誤認する。最後の全体確認は、両レーンが終わってから別に行う。
    """
    if pod_id:
        rp("pod", "delete", pod_id, check=False, timeout=300)
    for _ in range(10):
        rest = pods()
        mine = [q for q in rest if (q.get("id") or q.get("podId")) == pod_id]
        if not mine:
            others = [q.get("name") for q in rest]
            log(f"自分の Pod は消えた。pod list の残り: {others or '空'}")
            return True
        time.sleep(10)
    log(f"** 自分の Pod {pod_id} が消えない ** 手で消すこと")
    return False


def main():
    p = argparse.ArgumentParser(description="RunPod で1本走らせる")
    p.add_argument("--model", default="Qwen/Qwen3.5-9B",
                   help="カンマ区切りで複数指定すると、同じ Pod で順に回す "
                        "（2つ目からは vllm の導入が済んでいる分だけ速い）")
    p.add_argument("--stop-after-trials", type=int, default=0,
                   help="この試行数で意図的に止め、途中経過を残す（再開の試験用）")
    p.add_argument("--thinking", choices=("on", "off"), default="on")
    p.add_argument("--tasks", default="task_04,task_06")
    p.add_argument("--suite", default="v3_levels")
    p.add_argument("--conditions", default="")
    p.add_argument("--repeats", default="5")
    p.add_argument("--max-attempts", default="10")
    p.add_argument("--max-output-tokens", default="32768")
    p.add_argument("--max-model-len", default="65536")
    p.add_argument("--max-usd", type=float, default=2.0,
                   help="この金額を超えないところで打ち切る")
    p.add_argument("--cloud", choices=("COMMUNITY", "SECURE"), default="COMMUNITY")
    p.add_argument("--image", default=IMAGE)
    p.add_argument("--disk", type=int, default=60)
    p.add_argument("--volume", type=int, default=0)
    p.add_argument("--name", default="rot-smoke")
    p.add_argument("--out", default=str(BENCH / "results" / "runpod"))
    p.add_argument("--carry", default="", help="持ち込む途中経過のディレクトリ")
    p.add_argument("--commit", default="",
                   help="clone をこのコミットに固定する。中断した測定を続けるときは、"
                        "途中経過の指紋にあるコミットを渡すこと")
    p.add_argument("--use-local", action="store_true",
                   help="push していない手元のコードを clone の上に被せる")
    p.add_argument("--terminate-margin", type=int, default=600,
                   help="自動終了を予算より何秒あとに置くか")
    p.add_argument("--create-retries", type=int, default=60,
                   help="Pod を取れるまで試す回数。掴む前は課金されない")
    p.add_argument("--create-wait", type=int, default=60,
                   help="取れなかったときに待つ秒数")
    p.add_argument("--dry-run", action="store_true", help="Pod を作らずに手順だけ出す")
    args = p.parse_args()

    rate = RATES[args.cloud]
    seconds = int(args.max_usd / rate * 3600)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    models = [m.strip() for m in args.model.split(",") if m.strip()]
    log(f"モデル {' → '.join(models)} / thinking {args.thinking} / 反復 {args.repeats}")
    log(f"上限 ${args.max_usd:.2f} = {seconds / 60:.0f} 分"
        f"（{args.cloud} ${rate}/h、{GPU_ID}）")
    env_vars = {
        "ROT_MODEL": models[0], "ROT_THINKING": args.thinking,
        "ROT_TASKS": args.tasks, "ROT_SUITE": args.suite,
        "ROT_CONDITIONS": args.conditions, "ROT_REPEATS": args.repeats,
        "ROT_MAX_ATTEMPTS": args.max_attempts,
        "ROT_MAX_OUTPUT_TOKENS": args.max_output_tokens,
        "ROT_MAX_MODEL_LEN": args.max_model_len,
        # 立ち上げに使う分を差し引いて、実行に充てる秒数を渡す
        "ROT_DEADLINE_SEC": str(max(60, seconds - 900)),
        "ROT_ROUTE": f"RunPod 経路 / runpod/runpod_run.py / {args.cloud} / {GPU_ID}",
    }
    if args.commit:
        env_vars["ROT_COMMIT"] = args.commit
    if args.stop_after_trials:
        env_vars["ROT_STOP_AFTER_TRIALS"] = str(args.stop_after_trials)
    if args.dry_run:
        log("dry-run: 以下を投げる予定（Pod は作らない）")
        for k, v in env_vars.items():
            log(f"    {k}={v}")
        log(f"  pod create --gpu-id '{GPU_ID}' --cloud-type {args.cloud}"
            f" --image {args.image}"
            f" --terminate-after <now+{seconds + args.terminate_margin}s>")
        log(f"  結果の降ろし先: {out_dir}")
        return 0

    # **同じ名前の Pod だけを見る。** 全体が空であることを条件にすると、
    # もう一方のレーンが走っている間は2レーン目を始められない。
    same = [q for q in pods() if q.get("name") == args.name]
    if same:
        raise SystemExit(f"同じ名前の Pod がある: {[q.get('id') for q in same]}。"
                         "先に片付けること（家訓: 使い捨て）")
    others = [q.get("name") for q in pods()]
    if others:
        log(f"他レーンの Pod が走っている: {others}（干渉しない）")

    started = time.time()
    pod_id = None
    clean = False
    try:
        pod_id = create(args, seconds)
        log(f"pod {pod_id}")
        user, host, port = ssh_info(pod_id, 900)
        if not wait_ssh(user, host, port, 900):
            raise SystemExit("SSH が通らない")

        subprocess.run(["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}",
                        "mkdir -p /workspace/out /workspace/carry /workspace/local"],
                       check=True, timeout=120)
        scp_up(user, host, port, HERE / "setup.sh", "/workspace/setup.sh")
        scp_up(user, host, port, HERE / "remote_run.py", "/workspace/remote_run.py")
        # 手元は Windows なので、改行が CRLF のまま上がると Pod の bash が
        # command not found で落ちる（実測）。上流の改行設定に頼らず、
        # 上げたあとに必ず落とす。
        subprocess.run(["ssh", *SSH_OPTS, "-p", str(port), f"{user}@{host}",
                        "sed -i 's/\\r$//' /workspace/setup.sh /workspace/remote_run.py"],
                       check=True, timeout=120)
        if args.use_local:
            for name in ("run_benchmark.py", "summarize.py", "prompts.json",
                         "count_thinking.py", "mock_client.py"):
                scp_up(user, host, port, BENCH / name, f"/workspace/local/{name}")
        if args.carry:
            for f in sorted(Path(args.carry).glob("partial_*.jsonl")):
                scp_up(user, host, port, f, f"/workspace/carry/{f.name}")

        # 複数モデルは同じ Pod で順に回す。取得と実行のたびに結果を降ろすので、
        # 途中で落ちても、そこまでは手元にある。
        for i, model in enumerate(models, 1):
            env_vars["ROT_MODEL"] = model
            remaining = seconds - (time.time() - started) - 300
            if remaining < 120:
                log(f"予算が尽きたので {model} は回さない")
                break
            log(f"--- [{i}/{len(models)}] {model} ---")
            code = run_remote(user, host, port, env_vars,
                              out_dir / f"remote_{model.replace('/', '_')}.log",
                              remaining)
            log(f"リモートの終了コード {code}")
            scp_down(user, host, port, "/workspace/out/.", out_dir)
    finally:
        elapsed = time.time() - started
        log(f"実時間 {elapsed / 60:.1f} 分 / 概算 ${elapsed / 3600 * rate:.2f}")
        clean = teardown(pod_id)
        (out_dir / "run_meta.json").write_text(json.dumps({
            "pod_id": pod_id, "cloud": args.cloud, "gpu": GPU_ID, "image": args.image,
            "rate_usd_per_hr": rate, "elapsed_sec": round(elapsed, 1),
            "estimated_usd": round(elapsed / 3600 * rate, 4),
            "max_usd": args.max_usd, "pod_list_empty": clean, "env": env_vars,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
