次を実行
python3 -m venv .venv　→仮想環境を作成
source .venv/bin/activate　→仮想環境を有効化
python -m pip install --upgrade pip　
python -m pip install -r requirements.txt　→必要機能のダウンロード

YOLO/ByteTrackを使用するため、実行時は必ず仮想環境を有効にする

## Windows / NVIDIA GPUで実行する

プロジェクトのフォルダで、PowerShellから次を実行します。仮想環境を有効化しなくても、`.venv` のPythonを直接指定できます。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt
```

GPU用の構成は、PyTorch 2.14.1 / torchvision 0.29.1（CUDA 13.0版）とONNX Runtime GPU 1.31.1です。CUDA 13.0に対応するNVIDIAドライバーが必要です。PyTorchに含まれるCUDA・cuDNNをONNX Runtimeにも読み込ませるため、CUDA Toolkitの別途インストールは不要です。

`rtmlib==0.0.16` は依存情報にCPU版の `onnxruntime` を指定しています。CPU版とGPU版は同じモジュールを使うため、上の順序でCPU版を削除してからGPU版を導入します。`pip check` はrtmlibの `onnxruntime` 不足を報告しますが、実行時には `onnxruntime-gpu` がその機能を提供します。後から `requirements.txt` をインストールした場合も、CPU版の削除とGPU版の再インストール（`--force-reinstall` を付ける）を行ってください。

起動は `rtmlib起動.cmd` のダブルクリック、または次のコマンドです。

```powershell
.\.venv\Scripts\python.exe gui.py
```

GUIの「実行デバイス（YOLO・姿勢推定）」で `cuda` を選ぶと、両方の推論をGPUで行います。`cpu` はCPU実行、初期値の `auto` は両方のGPU環境が利用可能な場合にGPUを選びます。GPU環境が不足している場合、`auto` は理由をログに表示してCPUを選び、`cuda` はエラーで停止します。CUDA DLLの読み込みに失敗した場合も、長いYOLO処理を始める前に停止します。

ログにはGPU名と、RTMLIBの検出・姿勢推定それぞれの実行プロバイダーを表示します。GPU実行では `CUDAExecutionProvider` が表示されます。動画の読み書きや追跡処理などは引き続きCPUも使用します。

導入方法・DLLの互換性は [PyTorch公式](https://pytorch.org/get-started/previous-versions/) と [ONNX Runtime公式](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) を参照してください。

## GUIから実行する

仮想環境を有効にした状態で、プロジェクトのフォルダから次を実行します。

```bash
python gui.py
```

macOSでは、プロジェクト内の `rtmlib起動.command` をダブルクリックしても起動できます。このファイルはプロジェクトの `.venv` を使ってGUIを開きます。`.venv` がない場合は、先に上記の手順で仮想環境と依存パッケージを準備してください。

GUIで入力動画と撮影日時取得用のサムネイルをファイル選択し、出力先フォルダとYOLO・姿勢推定・追跡の各設定を指定できます。入力用の親フォルダやファイル名を別々に設定する必要はありません。出力ファイル名は、出力先フォルダの最下層名を使って自動生成します。たとえばフォルダ名が `踏切左-7` の場合、`踏切左-7.mp4`、`踏切左-7-yolo.mp4`、`踏切左-7.csv`、`踏切左-7_metadata.txt` になります。現在の設定値を初期値として使用します。設定は `gui_settings.json` に保存され、次回起動時にも読み込まれます。「初期設定に戻す」を押すと、現在の初期値に戻ります。

「解析を開始」を押すと、保存した設定で処理を起動し、ウィンドウ下部にログを表示します。「解析を中断」を押すと、その時点で実行中の解析プロセスを終了します。GUIは解析処理とは別のPythonプロセスを起動するため、GUIを起動したPython環境に `requirements.txt` の依存パッケージが必要です。macOSでTkinterが利用できない場合は、PythonのTk対応版を使用してください。

進捗バーはYOLO処理を0〜50%、RTMLIB処理を50〜100%として表示します。

YOLOの進捗率は動画情報の総フレーム数を使った概算です。動画情報と実際に読み込めるフレーム数が異なる場合、完了時に50%へ飛ぶことがあります。事前のフレーム数カウントは行いません。YOLO終了時に実際の処理フレーム数をログに表示し、RTMLIBの進捗率はその数を基準に計算します。

解析完了時のログに、YOLO・RTMLIBそれぞれの分析時間（秒）と分析速度（フレーム/秒）を小数点以下2桁で表示します。分析時間には各段階のモデル初期化・動画読み込み・描画・結果保存を含みます。分析速度は、各段階で処理した総フレーム数をその分析時間で割って求めます。

GUIと解析ワーカーはどちらも `gui.py` から起動します。解析ワーカーはGUIが内部で起動するため、通常は `python gui.py` だけを実行します。


## 設定項目

以下はGUIの設定項目の説明です。設定値はGUIで編集できます。

- 入力動画とサムネイル: GUIでファイルを選びます。親フォルダとファイル名は選択内容から自動設定されます。
- 出力先フォルダ: GUIで選んだフォルダ内に結果を保存します。
- 出力ファイル名: 骨格動画、YOLO動画、CSV、メタデータの名前を出力先フォルダ名から自動生成します。
- `CSV_MAX_PERSONS`: CSVに用意する人物列の最大数です。必要な人数に合わせて変更してください。
- YOLOモデルサイズ: GUIの選択肢 `n`、`s`、`m`、`l`、`x` から選びます。対応する `yolo11?.pt` を設定し、初回実行時に必要なモデルが自動ダウンロードされます。初期値は `m` です。
- `YOLO_TRACKER`: トラッカー設定です。`bytetrack.yaml`を使用します。
- `YOLO_IMAGE_SIZE`: YOLOの入力解像度です。大きいほど小さい人物を検出しやすくなりますが、処理時間が増えます。
- `YOLO_CONFIDENCE`: YOLOの人物検出信頼度です。
- `YOLO_TRACK_ID`: 指定した場合、そのYOLO追跡IDを対象にします。`None`なら動画全体の移動量から自動選択します。
- `CROP_PADDING_RATIO`: 対象人物の上下左右に追加する余白です。`0.25`は25%です。
- `TARGET_SELECTION_MIN_FRAMES`: 自動選択の候補にする最低検出フレーム数です。

姿勢推定モデルはGUIの選択肢 `performance`、`balanced`、`lightweight` から選べます。上記以外の追跡・推定設定もGUIから変更できます。

RTMLibのモデルは、既存モードを基本に個別指定で上書きできます。既存モードの組み合わせは `performance` がRTMPose-X + YOLOX-X、`balanced` がRTMPose-M + YOLOX-M、`lightweight` がRTMPose-S + YOLOX-tinyです。`RTMPoseモデル` が `mode` なら既存モードのモデルを使います。手動ではRTMPose-t/s/m/l/xを選べます。`RTMPose入力解像度` が `mode` なら既存モードの解像度を使い、手動モデルがその解像度に対応しない場合はモデルが対応する解像度に合わせます。入力解像度はt/s/mが256×192、xが384×288で、lは256×192または384×288を選べます。モデルと対応しない解像度を指定した場合は、解析開始前に設定エラーを表示します。

`RTMLib人物検出器 YOLOX` も `mode` またはnano/tiny/s/m/l/xから選べます。nano/tinyは416×416、s/m/l/xは640×640のモデル入力解像度を使います。これはRTMLibの[人物検出モデル一覧](https://github.com/Tau-J/rtmlib#model-zoo)にあるYOLOXモデルです。人物検出の信頼度しきい値とNMSしきい値はscore 0.70、NMS IoU 0.45を自動適用します。rtmlib 0.0.16ではこの2値は3つのモード間で共通です。全動画を追跡するYOLO11のモデル・画像サイズ・信頼度・IoU設定は別の設定です。


選択した動画を処理し、選択した出力先フォルダに動画とCSVを保存します。

CSVは1行に1フレームを記録します。同じフレームに複数人いる場合は、`person_0_id`、`person_1_id`のように人物ごとの列へ横並びで保存します。各人物について17部位ごとの`x`、`y`、`score`が入ります。人物を検出できなかった列は空欄になります。

処理は次の2段階です。

1. 動画全体をYOLO + ByteTrackで先に処理し、中心位置、移動速度、バウンディングボックスの重なり（IoU）を組み合わせて安定したIDを付けます。全フレームの軌跡を集計し、動画全体で移動量が大きい人物を対象に決定してYOLO動画を保存します。
2. 動画を先頭から再度読み込み、1段階目で確定した対象人物の矩形だけをメモリ上でクロップし、その小さな画像をrtmlibへ渡します。クロップ左上座標を加算して元動画座標へ戻し、CSVと骨格動画を保存します。

中間クロップ動画は保存・再読み込みしません。17関節や姿勢形状はrtmlibの出力なので、YOLOだけを先に実行する1段階目では直接使えません。したがって、1段階目は中心速度と矩形情報でIDを安定化し、2段階目でrtmlibの骨格推定を行う構成です。

JSON はフレームごとに `persons` を持ち、各人物の17部位（鼻、左目、右目、左耳、右耳、左肩、右肩、左肘、右肘、左手首、右手首、左股関節、右股関節、左膝、右膝、左足首、右足首）を記録します。各部位には `x`、`y`、`score` が入ります。
