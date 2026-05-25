#!/bin/bash
# Build the macOS Electron package with a working npm executable.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

NPM_BIN="$(find_working_npm || true)"
if [ -z "$NPM_BIN" ]; then
  echo "错误: 未找到可用的 npm。请安装 Node.js，或用 NPM_BIN=/path/to/npm bash build-mac.sh 指定 npm。"
  exit 1
fi

echo "使用 npm: $NPM_BIN"
cd "$SCRIPT_DIR"
"$NPM_BIN" install
"$NPM_BIN" run build:mac
