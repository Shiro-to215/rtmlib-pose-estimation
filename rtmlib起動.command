#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
    echo "仮想環境が見つかりません: $PYTHON"
    echo "README.md の手順で .venv を作成し、requirements.txt をインストールしてください。"
    read -r -p "Enterキーを押すと閉じます... "
    exit 1
fi

cd "$SCRIPT_DIR" || exit 1
export PYTHONUNBUFFERED=1
"$PYTHON" "$SCRIPT_DIR/gui.py"
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo
    echo "起動または実行に失敗しました（終了コード: $EXIT_CODE）。"
    read -r -p "Enterキーを押すと閉じます... "
fi

exit "$EXIT_CODE"
