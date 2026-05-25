#!/bin/bash
# 将 Python 后端打包为单文件可执行程序，输出到 electron/backend/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

find_working_npm() {
  if [ -n "$NPM_BIN" ] && "$NPM_BIN" --version >/dev/null 2>&1; then
    echo "$NPM_BIN"
    return 0
  fi

  for candidate in "$(command -v npm || true)" /opt/homebrew/bin/npm /usr/local/bin/npm /usr/bin/npm; do
    if [ -n "$candidate" ] && [ -x "$candidate" ] && "$candidate" --version >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done

  return 1
}

if [ -z "$PYTHON_BIN" ]; then
  echo "错误: 未找到 python3，请先安装 Python 3.10+。"
  exit 1
fi

cd "$BACKEND_DIR"

echo "使用 Python: $PYTHON_BIN"

if [ ! -f "$BACKEND_DIR/static/index.html" ]; then
  NPM_BIN="$(find_working_npm || true)"
  if [ -z "$NPM_BIN" ]; then
    echo "错误: 未找到可用的 npm，且 static/index.html 不存在，无法构建前端静态文件。"
    echo "请安装 Node.js，或用 NPM_BIN=/path/to/npm bash build-backend.sh 指定 npm。"
    exit 1
  fi
  echo "使用 npm: $NPM_BIN"
  echo "[1/4] 构建前端静态文件..."
  (cd "$BACKEND_DIR/frontend" && "$NPM_BIN" install && "$NPM_BIN" run build)
else
  echo "[1/4] 前端静态文件已存在，跳过构建。"
fi

echo "[2/4] 安装 PyInstaller..."
"$PYTHON_BIN" -m pip install pyinstaller --quiet

echo "[3/4] 打包后端..."
"$PYTHON_BIN" -m PyInstaller --onefile --name backend \
  --add-data "platforms:platforms" \
  --add-data "core:core" \
  --add-data "api:api" \
  --add-data "services:services" \
  --add-data "static:static" \
  main.py

echo "[4/4] 复制产物到 electron/backend/"
mkdir -p "$SCRIPT_DIR/backend"
cp dist/backend* "$SCRIPT_DIR/backend/"

echo "完成! 可执行文件: $SCRIPT_DIR/backend/backend"
