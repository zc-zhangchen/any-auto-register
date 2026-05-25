#!/bin/bash
# 将 Python 后端打包为单文件可执行程序，输出到 electron/backend/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

if [ -z "$PYTHON_BIN" ]; then
  echo "错误: 未找到 python3，请先安装 Python 3.10+。"
  exit 1
fi

cd "$BACKEND_DIR"

echo "使用 Python: $PYTHON_BIN"

echo "[1/3] 安装 PyInstaller..."
"$PYTHON_BIN" -m pip install pyinstaller --quiet

echo "[2/3] 打包后端..."
"$PYTHON_BIN" -m PyInstaller --onefile --name backend \
  --add-data "platforms:platforms" \
  --add-data "core:core" \
  --add-data "api:api" \
  --add-data "services:services" \
  --add-data "static:static" \
  main.py

echo "[3/3] 复制产物到 electron/backend/"
mkdir -p "$SCRIPT_DIR/backend"
cp dist/backend* "$SCRIPT_DIR/backend/"

echo "完成! 可执行文件: $SCRIPT_DIR/backend/backend"
