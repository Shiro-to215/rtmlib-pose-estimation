次を実行
python3 -m venv .venv　→仮想環境を作成
source .venv/bin/activate　→仮想環境を有効化
python -m pip install --upgrade pip　
python -m pip install -r requirements.txt　→必要機能のダウンロード

YOLO/ByteTrackを使用するため、実行時は必ず仮想環境を有効にしてください。


`main.py` の次の設定を書き換えます。

```python
INPUT_ROOT = Path(".")
INPUT_VIDEO_NAME = "input.mp4"
OUTPUT_ROOT = Path(".")
OUTPUT_FOLDER_NAME = "pose_output"
OUTPUT_VIDEO_NAME = "output_pose.mp4"
OUTPUT_YOLO_VIDEO_NAME = "output_pose_yolo.mp4"
OUTPUT_CSV_NAME = "output_pose.csv"
CSV_MAX_PERSONS = 10
YOLO_MODEL = "yolo11m.pt"
YOLO_TRACKER = "bytetrack.yaml"
YOLO_IMAGE_SIZE = 1280
YOLO_CONFIDENCE = 0.20
YOLO_TRACK_ID = None
CROP_PADDING_RATIO = 0.25
TARGET_SELECTION_MIN_FRAMES = 15
```

- `INPUT_ROOT`: 動画を探し始める階層です。配下のフォルダも自動で探索します。
- `INPUT_VIDEO_NAME`: 探索する動画ファイル名です。
- `OUTPUT_ROOT`: 出力フォルダを作成する階層です。
- `OUTPUT_FOLDER_NAME`: 自動作成する新規フォルダ名です。
- `OUTPUT_VIDEO_NAME`: 骨格動画のファイル名です。
- `OUTPUT_YOLO_VIDEO_NAME`: YOLOの検出枠・追跡IDを描画した実験用動画のファイル名です。
- `OUTPUT_CSV_NAME`: 座標 CSV のファイル名です。Excelやスプレッドシートで開けます。
- `CSV_MAX_PERSONS`: CSVに用意する人物列の最大数です。必要な人数に合わせて変更してください。
- `YOLO_MODEL`: 人物検出モデルです。初回実行時に自動ダウンロードされます。
- `YOLO_TRACKER`: トラッカー設定です。`bytetrack.yaml`を使用します。
- `YOLO_IMAGE_SIZE`: YOLOの入力解像度です。大きいほど小さい人物を検出しやすくなりますが、処理時間が増えます。
- `YOLO_CONFIDENCE`: YOLOの人物検出信頼度です。
- `YOLO_TRACK_ID`: 指定した場合、そのYOLO追跡IDを対象にします。`None`なら動画全体の移動量から自動選択します。
- `CROP_PADDING_RATIO`: 対象人物の上下左右に追加する余白です。`0.25`は25%です。
- `TARGET_SELECTION_MIN_FRAMES`: 自動選択の候補にする最低検出フレーム数です。

推定モデルを設定する
[performance, balanced, lightweight]

設定後、[コードをセーブしてから]以下をターミナルで実行します。

`python3 main.py`





動画は `INPUT_ROOT` の配下を `pathlib` で階層探索します。同じ名前の動画が複数ある場合は、見つかった順に並べて最初の1つを処理します。出力先には `OUTPUT_ROOT / OUTPUT_FOLDER_NAME` を新規作成し、その中に動画とCSVを保存します。

CSVは1行に1フレームを記録します。同じフレームに複数人いる場合は、`person_0_id`、`person_1_id`のように人物ごとの列へ横並びで保存します。各人物について17部位ごとの`x`、`y`、`score`が入ります。人物を検出できなかった列は空欄になります。

処理は次の2段階です。

1. 動画全体をYOLO + ByteTrackで先に処理し、中心位置、移動速度、バウンディングボックスの重なり（IoU）を組み合わせて安定したIDを付けます。全フレームの軌跡を集計し、動画全体で移動量が大きい人物を対象に決定してYOLO動画を保存します。
2. 動画を先頭から再度読み込み、1段階目で確定した対象人物の矩形だけをメモリ上でクロップし、その小さな画像をrtmlibへ渡します。クロップ左上座標を加算して元動画座標へ戻し、CSVと骨格動画を保存します。

中間クロップ動画は保存・再読み込みしません。17関節や姿勢形状はrtmlibの出力なので、YOLOだけを先に実行する1段階目では直接使えません。したがって、1段階目は中心速度と矩形情報でIDを安定化し、2段階目でrtmlibの骨格推定を行う構成です。

JSON はフレームごとに `persons` を持ち、各人物の17部位（鼻、左目、右目、左耳、右耳、左肩、右肩、左肘、右肘、左手首、右手首、左股関節、右股関節、左膝、右膝、左足首、右足首）を記録します。各部位には `x`、`y`、`score` が入ります。