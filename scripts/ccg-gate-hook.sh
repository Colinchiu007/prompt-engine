#!/bin/sh
# 质量节拍 — CCG 质量门禁钩子
#
# 由 scripts/install-ccg-gate-hook.sh 安装到 .git/hooks/pre-commit。
# 本钩子只跑 CCG 门禁；项目自身原有的检查请保留在各自的位置。
#
#   门禁：verify-security（阻断）/ verify-change、verify-quality（告警）
#   豁免：SKIP_CCG_GATE=1 git commit
set -u

# 本文件位于 <repo>/scripts/ 下，门禁脚本与它同目录
SCRIPT_DIR="$(cd "$(dirname -- "$0")" && pwd)"
GATE_SCRIPT="$SCRIPT_DIR/ccg-gate.js"

# git 钩子不继承登录 shell 的 PATH，node 常常找不到
if ! command -v node >/dev/null 2>&1; then
  if [ -d "$HOME/.fnm" ]; then
    eval "$(fnm env --shell sh 2>/dev/null)" 2>/dev/null || true
  fi
fi
if ! command -v node >/dev/null 2>&1; then
  for p in \
    "$HOME/AppData/Local/hermes/node" \
    "/c/Users/$USER/AppData/Local/hermes/node" \
    "/d/Program Files/npm-global"
  do
    [ -d "$p" ] && export PATH="$p:$PATH"
  done
fi

if ! command -v node >/dev/null 2>&1; then
  echo "[CCG] WARN 找不到 node，CCG 门禁未执行"
  exit 0
fi

if [ ! -f "$GATE_SCRIPT" ]; then
  echo "[CCG] WARN 门禁未启用：找不到 $GATE_SCRIPT"
  exit 0
fi

exec node "$GATE_SCRIPT"