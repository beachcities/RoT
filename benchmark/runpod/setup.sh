#!/usr/bin/env bash
# RunPod の Pod 上で1回だけ走る仕掛け。
#
# Colab 経路（colab/remote_run.py）との違いは、セッションの上限が無いことだけで、
# 測っているものは同じ。**同じイメージ・同じこのスクリプトを煙試験と本走行の
# 両方で使う。** 煙試験で測った所要をそのまま本走行の見積りに使えるようにするため。
#
# 秘密は環境変数で渡す。**このスクリプトは値を出力しない。**
set -u
export PYTHONUNBUFFERED=1
export HF_HOME=/workspace/hf
export PIP_DISABLE_PIP_VERSION_CHECK=1

# イメージのシステム Python は PEP 668 で外部管理扱いになっており、素の pip が
# externally-managed-environment で拒む（実測）。**venv を切るとイメージ同梱の
# torch が見えなくなる**ので、システム側にそのまま入れる。
PIP="pip install -q --break-system-packages"

BENCH=/workspace/RoT/benchmark
mkdir -p /workspace/out "$HF_HOME"
# 1つの Pod で複数モデルを順に回すので、計測はモデルごとに分けて残す。
TAG=$(echo "${ROT_MODEL}" | tr '/:' '__')
STAMP=/workspace/out/timings_${TAG}.json

log() { echo "[setup] $*"; }
now() { date +%s; }

t0=$(now)
if ! python3 -c "import vllm" 2>/dev/null; then
  log "vllm を入れる"
  # イメージ同梱の torch と食い違うと import 経路で落ちる。Colab で実測した
  # 対処と同じで、音声系は使わないので外す。
  pip uninstall -y -q --break-system-packages torchaudio 2>/dev/null || true
  $PIP vllm "huggingface_hub[hf_transfer]" openai python-dotenv || {
    log "vllm の導入に失敗した"; echo '{"phase":"vllm_install","ok":false}' > "$STAMP"; exit 1; }
else
  log "vllm は同梱されている"
  $PIP "huggingface_hub[hf_transfer]" openai python-dotenv 2>/dev/null || true
fi
t_install=$(( $(now) - t0 ))
log "vllm 導入まで ${t_install}s"

if [ ! -d /workspace/RoT ]; then
  git clone --depth 1 https://github.com/beachcities/RoT.git /workspace/RoT || exit 1
fi
# push していない手元のコードがあれば被せる（clone との差分になり、指紋に dirty と残る）
if [ -d /workspace/local ] && [ -n "$(ls -A /workspace/local 2>/dev/null)" ]; then
  cp -v /workspace/local/* "$BENCH"/ 2>/dev/null | sed 's/^/[setup] 被せた: /'
fi

# 取得を実行と分けて計る。帯域と所要を煙試験で押さえるのが目的。
t1=$(now)
export HF_HUB_ENABLE_HF_TRANSFER=1
log "モデルを取得する: ${ROT_MODEL}"
python3 - <<'PY' || exit 1
import os, sys
from huggingface_hub import snapshot_download
try:
    path = snapshot_download(os.environ["ROT_MODEL"], max_workers=8)
except Exception as exc:
    print(f"[setup] 取得に失敗: {type(exc).__name__}: {exc}")
    sys.exit(1)
print(f"[setup] 取得先 {path}")
PY
t_fetch=$(( $(now) - t1 ))
bytes=$(du -sb "$HF_HOME" 2>/dev/null | cut -f1)
log "取得まで ${t_fetch}s / ${bytes} bytes"

python3 - "$t_install" "$t_fetch" "$bytes" "$STAMP" <<'PY'
import json, sys
json.dump({"vllm_install_sec": int(sys.argv[1]), "model_fetch_sec": int(sys.argv[2]),
           "hf_home_bytes": int(sys.argv[3] or 0)},
          open(sys.argv[4], "w"), ensure_ascii=False)
PY

cd "$BENCH" || exit 1
exec python3 -u /workspace/remote_run.py
