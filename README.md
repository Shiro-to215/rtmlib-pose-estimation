次を実行
python3 -m venv .venv　→仮想環境を作成
source .venv/bin/activate　→仮想環境を有効化
python -m pip install --upgrade pip　
python -m pip install -r requirements.txt　→必要機能のダウンロード


`main.py` の次の設定を書き換えます。

```python
INPUT_ROOT = Path(".")
INPUT_VIDEO_NAME = "input.mp4"
OUTPUT_ROOT = Path(".")
OUTPUT_FOLDER_NAME = "pose_output"
OUTPUT_VIDEO_NAME = "output_pose.mp4"
OUTPUT_JSON_NAME = "output_pose.json"
```

- `INPUT_ROOT`: 動画を探し始める階層です。配下のフォルダも自動で探索します。
- `INPUT_VIDEO_NAME`: 探索する動画ファイル名です。
- `OUTPUT_ROOT`: 出力フォルダを作成する階層です。
- `OUTPUT_FOLDER_NAME`: 自動作成する新規フォルダ名です。
- `OUTPUT_VIDEO_NAME`: 骨格動画のファイル名です。
- `OUTPUT_JSON_NAME`: 座標 JSON のファイル名です。

推定モデルを設定する
[performance, balanced, lightweight]

設定後、[コードをセーブしてから]以下をターミナルで実行します。

`python3 main.py`

動画は `INPUT_ROOT` の配下を `pathlib` で階層探索します。同じ名前の動画が複数ある場合は、見つかった順に並べて最初の1つを処理します。出力先には `OUTPUT_ROOT / OUTPUT_FOLDER_NAME` を新規作成し、その中に動画と JSON を保存します。

JSON はフレームごとに `persons` を持ち、各人物の17部位（鼻、左目、右目、左耳、右耳、左肩、右肩、左肘、右肘、左手首、右手首、左股関節、右股関節、左膝、右膝、左足首、右足首）を記録します。各部位には `x`、`y`、`score` が入ります。