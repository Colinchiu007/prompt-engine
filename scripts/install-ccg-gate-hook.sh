#!/bin/sh
# 安装 CCG 质量门禁钩子到 .git/hooks/pre-commit
# 用法：sh scripts/install-ccg-gate-hook.sh
set -eu
ROOT="$(cd "$(dirname -- "$0")/.." && pwd)"
mkdir -p "$ROOT/.git/hooks"
cat > "$ROOT/.git/hooks/pre-commit" <<'HOOK'
#!/bin/sh
exec "$(cd "$(dirname -- "$0")" && pwd)/../../scripts/ccg-gate-hook.sh"
HOOK
chmod +x "$ROOT/.git/hooks/pre-commit" 2>/dev/null || true
echo "已安装: .git/hooks/pre-commit"