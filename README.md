# 動画姿勢推定アプリ（YOLO11 + ByteTrack + RTMPose / ViTPose++）

動画から人物を検出・追跡し、主要人物1名の17関節キーポイント（COCO形式）を推定して骨格動画・姿勢推論用crop動画2本（骨格なし／骨格あり）・CSVデータ・動画メタデータを出力するデスクトップアプリケーションです。
姿勢推定エンジンは高速・省メモリな **RTMPose（RTMLib / ONNX Runtime）** と、研究向け高精度な **ViTPose++（PyTorch / Hugging Face Transformers）** を切り替えられます。
デスクトップUIは **PyWebView + React/Vite** で構成されており、複数動画の予約登録・連続自動解析・中断/再開・パラメータ検索・ドラッグ＆ドロップに対応しています。

---

## 目次

- [1. 動作環境と対応構成](#1-動作環境と対応構成)
- [2. 新規パソコンでの事前準備（ダウンロード・リンク一覧）](#2-新規パソコンでの事前準備ダウンロードリンク一覧)
  - [2.1 必須ソフトウェア](#21-必須ソフトウェア)
  - [2.2 OS・実行環境別の追加ソフトウェア](#22-os実行環境別の追加ソフトウェア)
  - [2.3 任意ツール（撮影日時の取得用）](#23-任意ツール撮影日時の取得用)
  - [2.4 開発者向けツール（UIを編集・再ビルドする場合のみ）](#24-開発者向けツールuiを編集再ビルドする場合のみ)
- [3. 初期構築からアプリ起動までの手順](#3-初期構築からアプリ起動までの手順)
  - [3.1 リポジトリの取得](#31-リポジトリの取得)
  - [3.2 Windows（NVIDIA GPU版・推奨・高速）](#32-windowsnvidia-gpu版推奨高速)
  - [3.3 Windows（CPU版）](#33-windowscpu版)
  - [3.4 macOS（CPU版）](#34-macoscpu版)
  - [3.5 GPU環境とCPU環境についての補足・切り替え](#35-gpu環境とcpu環境についての補足切り替え)
- [4. アプリの使い方（GUI操作ガイド）](#4-アプリの使い方gui操作ガイド)
  - [4.1 画面構成](#41-画面構成)
  - [4.2 基本の流れ（予約〜連続解析）](#42-基本の流れ予約連続解析)
  - [4.3 中断・失敗・重複回避・自動保存の仕様](#43-中断失敗重複回避自動保存の仕様)
  - [4.4 実行ログ・進捗バー・デバイスの挙動](#44-実行ログ進捗バーデバイスの挙動)
- [5. 設定項目の説明](#5-設定項目の説明)
- [6. 出力ファイル・CSV仕様・2段階処理の仕組み](#6-出力ファイルcsv仕様2段階処理の仕組み)
  - [6.1 出力ファイル一覧](#61-出力ファイル一覧)
  - [6.2 CSVフォーマット](#62-csvフォーマット)
  - [6.3 2段階処理アーキテクチャ](#63-2段階処理アーキテクチャ)
- [7. 開発者向け情報（コマンドオプション・UI開発・自動テスト）](#7-開発者向け情報コマンドオプションui開発自動テスト)
- [8. トラブルシューティング](#8-トラブルシューティング)

---

## 1. 動作環境と対応構成

| OS | 対応実行モード | 使用する依存定義 | 起動方法 |
| --- | --- | --- | --- |
| **Windows 10 / 11** | **NVIDIA GPU (CUDA 13.0)** | `requirements-gpu.txt` + `rtmlib` (`--no-deps`) | `rtmlib起動.cmd` または `.\.venv\Scripts\python.exe gui.py` |
| **Windows 10 / 11** | **CPU** | `requirements.txt` | `rtmlib起動.cmd` または `.\.venv\Scripts\python.exe gui.py` |
| **macOS** (Apple Silicon / Intel) | **CPU** | `requirements.txt` | `rtmlib起動.command` または `python gui.py` |

> **macOSでのGPUについて**
> 本アプリの推論制御（`DEVICE` 設定）は `auto` / `cpu` / `cuda` に対応しています。macOS は NVIDIA CUDA 非対応のため、`auto`（初期値）を選択すると自動的に CPU 実行になります。

---

## 2. 新規パソコンでの事前準備（ダウンロード・リンク一覧）

新しいパソコンで初めて環境を作る場合は、以下のソフトウェアを先に用意してください。

### 2.1 必須ソフトウェア

| 項目 | ダウンロード先・導入方法 | 備考 |
| --- | --- | --- |
| **Python（3.11〜3.14）** | [Python 公式ダウンロード](https://www.python.org/downloads/) | GPU版の `onnxruntime-gpu` が **Python 3.11以上**、PyTorch / torchvision の構成が `!=3.14.1` を要求します（**3.14.10 で動作確認済み**）。<br>**Windows注意点**: インストーラー最初の画面下部 **「Add python.exe to PATH」に必ずチェック** を入れてください。 |
| **本リポジトリのソースコード** | [GitHub リポジトリページ](https://github.com/Shiro-to215/rtmlib-pose-estimation) | Git で `clone` するか、緑色の「`<> Code`」→「`Download ZIP`」で取得します（次章参照）。 |
| **Git**（`git clone` を使う場合） | [Git 公式ダウンロード](https://git-scm.com/downloads) | ZIP ダウンロードで済ませる場合は不要です（macOS は後述の Command Line Tools に含まれます）。 |

> **初回解析時の自動ダウンロード（インターネット接続）**
> YOLO11 の重みファイル（`yolo11*.pt`）、RTMPose のモデル（ONNX zip）、および ViTPose++ のモデル（Hugging Face Hub の `usyd-community/vitpose-plus-*`）は Git には含まれていません。**各モデルの初回解析実行時に自動的にダウンロード**されるため、初回実行時はインターネットに接続した状態で行ってください。
> なお、ViTPose++ は 2回目以降ローカルキャッシュを優先読み込み（`local_files_only=True`）するため、ネットワーク通信なしでオフライン動作します。

### 2.2 OS・実行環境別の追加ソフトウェア

| 対象 | 項目 | ダウンロード先・備考 |
| --- | --- | --- |
| **Windows (NVIDIA GPU版)** | **NVIDIA グラフィックスドライバー** | [NVIDIA ドライバーダウンロード](https://www.nvidia.com/ja-jp/drivers/)<br>CUDA 13.0 に対応する最新の公式ドライバーをインストールしてください。PyTorch に CUDA / cuDNN が同梱されており ONNX Runtime からも読み込むため、**CUDA Toolkit の別途インストールは不要**です。 |
| **Windows 10 等** | **Microsoft Edge WebView2 ランタイム** | [Edge WebView2 公式ページ](https://developer.microsoft.com/ja-jp/microsoft-edge/webview2/)（ページ内の「エバーグリーン スタンドアロン インストーラー」等）<br>Windows 11 は標準搭載のため通常不要です。Windows 10 でアプリウィンドウが開かない場合のみ導入してください。 |
| **macOS** | **Xcode Command Line Tools**（必要時のみ） | ターミナルで `xcode-select --install`<br>`pip install` 時にビルドが必要になった場合や `git` コマンドを使う場合のみ導入します。 |

### 2.3 任意ツール（撮影日時の取得用）

解析結果の `*_metadata.txt` に動画（または指定サムネイル画像）の撮影日時を書き込む場合、`exiftool`（優先）または `ffprobe`（FFmpeg同梱）を使用します。未導入でも解析自体は正常に完了します（撮影日時欄が `取得不可` になります）。

- **ExifTool**（推奨・Sony製カメラのサムネイル画像からの取得にも対応）: [ExifTool 公式](https://exiftool.org/)
  - Windows (`winget`): `winget install OliverBetz.ExifTool`（導入後、新しいターミナルを開き直してください）
  - macOS (`Homebrew`): `brew install exiftool`
- **FFmpeg / ffprobe**: [FFmpeg 公式ダウンロード](https://ffmpeg.org/download.html)
  - Windows (`winget`): `winget install Gyan.FFmpeg`
  - macOS (`Homebrew`): `brew install ffmpeg`

### 2.4 開発者向けツール（UIを編集・再ビルドする場合のみ）

通常利用者はビルド済みフロントエンド（`frontend/dist/`）がリポジトリに含まれているため **Node.js の導入は不要** です。React/TypeScript 画面をカスタマイズする場合のみ導入してください。

- **Node.js（LTS推奨）**: [Node.js 公式ダウンロード](https://nodejs.org/)

---

## 3. 初期構築からアプリ起動までの手順

### 3.1 リポジトリの取得

#### 方法1：Git で取得する場合（推奨）

Windows（PowerShell）または macOS（ターミナル）で作業したいフォルダに移動し、以下を実行します。

```bash
git clone https://github.com/Shiro-to215/rtmlib-pose-estimation.git
cd rtmlib-pose-estimation
```

#### 方法2：ZIP でダウンロードする場合

1. [GitHub リポジトリページ](https://github.com/Shiro-to215/rtmlib-pose-estimation) を開き、**「`<> Code`」→「`Download ZIP`」** をクリックします。
2. ダウンロードした ZIP ファイルを展開し、展開されたフォルダ（`gui.py` が入っているフォルダ）をターミナル／PowerShell で開きます。

---

### 3.2 Windows（NVIDIA GPU版・推奨・高速）

プロジェクトのフォルダで **PowerShell** を開き、以下を上から順番に実行します。仮想環境を有効化（`Activate.ps1`）しなくても、`.venv` 内の Python を直接指定して実行できます。

```powershell
# 1. 仮想環境 (.venv) を作成
python -m venv .venv

# 2. pip を最新化
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# 3. GPU版に必要なパッケージを一括インストール（CUDA 13.0版 PyTorch + ONNX Runtime GPU + UI）
.\.venv\Scripts\python.exe -m pip install -r requirements-gpu.txt

# 4. rtmlib を CPU版 onnxruntime の自動導入をスキップしてインストール
.\.venv\Scripts\python.exe -m pip install --no-deps rtmlib==0.0.16
```

**アプリを起動する：**

- フォルダ内の **`rtmlib起動.cmd` をダブルクリック**
- または PowerShell から次を実行：

```powershell
.\.venv\Scripts\python.exe gui.py
```

---

### 3.3 Windows（CPU版）

NVIDIA 製 GPU を搭載していない Windows PC の場合は、PowerShell で以下を実行します。

```powershell
# 1. 仮想環境 (.venv) を作成
python -m venv .venv

# 2. pip を最新化
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# 3. CPU版の依存パッケージを一括インストール
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**アプリを起動する：**

- フォルダ内の **`rtmlib起動.cmd` をダブルクリック**
- または PowerShell から `.\.venv\Scripts\python.exe gui.py` を実行

---

### 3.4 macOS（CPU版）

プロジェクトのフォルダで **ターミナル** を開き、以下を上から順番に実行します。

```bash
# 1. 仮想環境 (.venv) を作成
python3 -m venv .venv

# 2. 仮想環境を有効化
source .venv/bin/activate

# 3. pip を最新化
python -m pip install --upgrade pip

# 4. 依存パッケージを一括インストール
python -m pip install -r requirements.txt
```

> **`python3` の確認**
> Homebrew を利用している場合で `python3` が見つからないときは `brew install python` で導入できます（[Homebrew公式](https://brew.sh/)）。

**アプリを起動する：**

- **コマンドから起動する場合**（仮想環境を有効化した状態で実行）：
  ```bash
  source .venv/bin/activate
  python gui.py
  ```
  ※ 仮想環境を有効化せず `./.venv/bin/python gui.py` でも起動できます。
- **ダブルクリックで起動する場合（`rtmlib起動.command`）**：
  GitHub から ZIP ダウンロードした場合など、初回は実行権限がないことがあるため、一度だけターミナルで権限を付与してください。
  ```bash
  chmod +x rtmlib起動.command
  ```
  その後 Finder から `rtmlib起動.command` をダブルクリックします（初回に「開発元が未確認」等の警告が出た場合は、ファイルを **右クリック（Control＋クリック）→「開く」** で起動できます）。

---

### 3.5 GPU環境とCPU環境についての補足・切り替え

#### GPU版（`requirements-gpu.txt`）の技術構成と `--no-deps` の理由

- GPU用の構成は **PyTorch 2.14.1 / torchvision 0.29.1（CUDA 13.0版）**・**ONNX Runtime GPU 1.31.1**・**Transformers 4.49.0以上（ViTPose++ 用）** です。RTMPose 実行時に PyTorch に含まれる CUDA・cuDNN DLL を `onnxruntime-gpu` にも読み込ませるため（[gui.py](gui.py) 内の `ort.preload_dlls()`）、CUDA Toolkit の別途インストールは不要です。
- `rtmlib==0.0.16` はパッケージの依存情報に CPU版の `onnxruntime` を指定しています。CPU版 `onnxruntime` と GPU版 `onnxruntime-gpu` は同じ Python モジュール名（`onnxruntime`）を上書き共有するため、同時に導入すると GPU 推論が壊れます。
- そのため GPU 環境では、必要な依存（`opencv-contrib-python`・`numpy`・`tqdm`・`transformers` 等）を含めた `requirements-gpu.txt` を先に入れ、`rtmlib==0.0.16` のみ `--no-deps` で導入する手順としています。
- この構成では `pip check` が「`rtmlib` に `onnxruntime` が不足している」と報告することがありますが、実行時には `onnxruntime-gpu` がその機能を提供するため正常動作します。

#### 既存の CPU 環境から GPU 環境へ切り替える場合（Windows）

誤って `requirements.txt` を先に入れてしまった場合や、CPU 環境を GPU 環境へ作り直す場合は、CPU版 `onnxruntime` を削除したうえで GPU版を導入してください（`--force-reinstall` 推奨）：

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
.\.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements-gpu.txt
.\.venv\Scripts\python.exe -m pip install --no-deps rtmlib==0.0.16
```

#### GPU環境を維持したまま新機能パッケージだけを追加する場合

既に動作中の旧 GPU 環境（`.venv`）をアップデートする場合は、`requirements.txt` を再実行せず不足パッケージだけを追加してください（`requirements.txt` を実行すると CPU版 `onnxruntime` が再導入されてしまいます）：

```powershell
.\.venv\Scripts\python.exe -m pip install "pywebview>=6.0" "transformers>=4.49.0"
```

導入方法や互換性の詳細は [PyTorch公式](https://pytorch.org/get-started/previous-versions/) および [ONNX Runtime公式（CUDA Execution Provider）](https://onnxruntime.ai/docs/execution-providers/CUDA-Execution-Provider.html) を参照してください。

---

## 4. アプリの使い方（GUI操作ガイド）

### 4.1 画面構成

アプリを起動すると、上部バー＋左右2ペインの画面が開きます。

1. **上部アクションバー**
   - **`▶ 解析開始`**: 予約リストの先頭にある待機動画から順番に自動解析を開始します。
   - **`■ 解析中断`**: 現在実行中の解析プロセスを停止し、その動画を予約リストの先頭（待機中）へ戻します。
   - 右側のステータスバナーに現在の状態・進捗率が表示されます。
2. **左ペイン（解析中モニター）** — 設定画面などを開いている間も常に表示されます。
   - ステータスバッジ（`待機中` / `解析実行中` / `YOLO 処理中` / `RTMPose 処理中` / `ViTPose++ 処理中` / `中断処理中`）
   - 16:9 動画プレビュー・動画名・出力フォルダー名・解像度
   - 円形進捗バー（0〜50%: YOLO 人物検出・追跡 / 50〜100%: 選択したエンジン（RTMPose / ViTPose++）の骨格推定）
   - 実行ログ欄（クリアボタン付き）
3. **右ペイン（ワークスペース）** — 以下の3画面を切り替えて操作します。
   - **`予約リスト`**: 登録済みの動画カード一覧（各カードに姿勢推定モデル・YOLOサイズ・デバイスを表示）、`削除`・`上へ`・`下へ`・`基本設定` ツールバー、点線枠 `＋ 予約を追加`
   - **`予約を追加`**: 動画選択・出力先指定・サムネイル指定（下部に適用される初期設定サマリー表示）
   - **`基本設定` / 個別 `設定`**: 検索バー＋3つの設定タブ（検索バー入力時は3タブの全項目を1画面に展開表示）

### 4.2 基本の流れ（予約〜連続解析）

1. **既定の出力先や初期条件を設定する（初回推奨）**
   - 予約リスト右上の **`基本設定`** をクリックし、「新規予約時の既定出力親フォルダー」や実行デバイス・モデル等の初期条件を確認し、**`基本設定を保存`** を押します（`gui_settings.json` に保存され、次回起動時にも読み込まれます）。
2. **解析したい動画を予約に追加する**
   - 点線枠 **`＋ 予約を追加`** をクリックする（または点線枠へ動画ファイルをドラッグ＆ドロップする）と追加画面が開きます。
   - **`動画ファイルを選択…`**（または枠内へのドロップ）で動画を1本または複数本選択します。
   - **1本選択時**: 出力先フォルダー名を直接指定でき、生成される5つのファイル名プレビューと、任意の「撮影日時取得用サムネイル画像（Sony製カメラの `.JPG` 等）」を指定できます。
   - **複数本選択時**: 出力親フォルダーを指定すると、その配下に動画ごとのサブフォルダーが自動作成されます。
   - **`予約リストに追加する`** を押すと予約リストに登録されます。
3. **順番・個別設定を調整する**
   - 予約リストの各行をクリックして選択（`Ctrl` / `Shift` での複数選択も可）し、**`上へ` / `下へ`** またはカードのドラッグ＆ドロップで実行順を並べ替え、**`削除`** で不要な予約を外せます（元動画や出力済みファイルは削除しません）。
   - 待機中または失敗した動画は、各カードの **`設定`** ボタンから予約追加後でも出力先やモデル・追跡条件を個別に編集できます（`基本設定を反映` ボタンで現在の基本設定を読み込むこともできます）。
4. **解析を開始する**
   - 上部バーの **`▶ 解析開始`** を押すと、待機中の予約を上から順に自動実行します。
   - 解析実行中でも、右ペインで新しい予約の追加や未実行予約の編集を行えます。

### 4.3 中断・失敗・重複回避・自動保存の仕様

- **完了後の表示**: 正常に解析が完了した動画は予約リストから自動で非表示になります（出力先フォルダーの解析結果はそのまま保持されます）。
- **失敗時の再実行**: エラーで失敗した動画は赤いカードで予約リストに残り、エラー要旨の確認、**`設定`** からの条件見直し、**`再試行`** ボタンでの再待機化が行えます。
- **中断と再開**: **`■ 解析中断`** を押す（または解析中にアプリを閉じる）と実行中のプロセスを停止し、その動画を待機中の先頭へ戻します。再実行時はその動画の先頭からやり直します。
- **フォルダ重複の自動回避**: 出力先フォルダーが既に存在する場合（中断後の再実行や同名動画など）は、既存結果を上書きしないよう `_2`、`_3` のように連番付きフォルダーへ自動変更して保存します。
- **状態と設定の自動保存**:
  - 基本設定は `gui_settings.json` に保存されます。
  - 予約一覧・登録順・状態・個別設定は `analysis_queue.json` に自動保存され、次回起動時に復元されます（前回解析中だった予約も自動で待機中の先頭へ戻ります）。
  - 実行時の設定スナップショットは `.analysis_jobs/configs/`、予約ごとの詳細ログは `.analysis_jobs/logs/` に保存されます（いずれも `.gitignore` 対象）。

### 4.4 実行ログ・進捗バー・デバイスの挙動

- **実行デバイス（`DEVICE`）の挙動**:
  - `auto`（初期値）: `POSE_ENGINE = rtmpose` の場合は PyTorch CUDA と ONNX Runtime CUDA（`CUDAExecutionProvider`）が両方使える場合に GPU を選択し、`POSE_ENGINE = vitpose` の場合は PyTorch CUDA が使える場合に GPU を選択します。GPU 環境が不足している場合は、理由をログに表示して自動的に CPU を選択します。
  - `cuda`: 両方の推論（YOLO + 姿勢推定モデル）を GPU で実行します。GPU 環境が不足している場合はエラーで停止します。CUDA DLL の読み込みや姿勢推定モデルの CUDA 初期化に失敗した場合も、長い YOLO 処理を始める前に停止します。
  - `cpu`: 両方の推論を CPU で実行します。
  - 実行ログには、`実行デバイス: CUDA:0 (<GPU名>)`（または `CPU`）、`姿勢モデル: RTMPose-...` / `ViTPose++-...`、各段階の実行バッチサイズ（VRAM 空き容量による自動制限・OOM 発生時の自動半減フォールバックを含む）、および `mp4v` 制限に伴う FPS 調整時（`動画書き出しFPS調整`）のメッセージを表示します。なお動画のデコード・エンコードや追跡処理などは引き続き CPU も使用します。
- **進捗バー**:
  - `0〜50%`: YOLO 処理（動画情報の総フレーム数を使った概算です。動画ヘッダ情報と実際に読み込めるフレーム数が異なる場合、完了時に 50% へ飛ぶことがあります）。
  - `50〜100%`: 姿勢推定処理（RTMPose / ViTPose++。YOLO 終了時にログへ表示する「実処理フレーム数」を基準に計算します）。
- **分析速度ログ**:
  - 解析完了時のログに、YOLO と選択した姿勢推定エンジン（`RTMPose` または `ViTPose++`）それぞれの分析時間（秒）と分析速度（フレーム/秒）を小数点以下2桁で表示します。分析時間にはモデル初期化・動画読み込み・描画・結果保存を含みます。

---

## 5. 設定項目の説明

設定画面（`基本設定`／個別 `設定`）には上部検索バー（キーワード入力時は3タブの全項目を1画面に展開表示）と3つのタブがあります。

### タブ1：基本・出力設定

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `POSE_ENGINE` | 姿勢推定エンジン | `rtmpose` | `RTMPose`（高速・省メモリ / ONNX）または `ViTPose++`（研究用・最高精度 / PyTorch）から選択します。非選択側の設定も保持されます。 |
| `DEVICE` | 推論実行デバイス | `auto` | `auto`（自動判定）/ `cpu` / `cuda` から選択します。 |
| `CSV_MAX_PERSONS` | CSV出力の最大人数列数 | `3` | CSV に用意する人物列の最大数（1〜20）です。必要な人数に合わせて変更してください。 |

**YOLO 検出・しきい値設定**

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `YOLO_MODEL` | YOLOモデル | `yolo11m.pt` | `n`（最速）〜 `x`（最高精度）を選択します。初回実行時に自動ダウンロードされます。 |
| `YOLO_BATCH_SIZE` | YOLO バッチサイズ | `1` | YOLO11 で一度に推論するフレーム数（`1`〜`512`）。CPU 実行時は `1` に固定され、空き VRAM 容量による自動調整・CUDA メモリ不足（OOM）時の半減フォールバックを行います。 |
| `YOLO_IMAGE_SIZE` | YOLO 入力解像度 | `1280` | YOLO の入力解像度（`320`〜`2560` px, 32刻み）。大きいほど小さい人物・遠景を検出しやすくなりますが処理時間が増えます。 |
| `YOLO_CONFIDENCE` | YOLO 検出信頼度 | `0.20` | YOLO の人物検出信頼度しきい値（`0.01`〜`1.0`）。 |
| `YOLO_IOU` | YOLO NMS IoU しきい値 | `0.50` | YOLO の NMS IoU しきい値。重複ボックスの除外基準です。 |
| `CROP_PADDING_RATIO` | 人物クロップ余白率 | `0.25` | 対象人物を切り出して姿勢推定エンジンへ渡す際に上下左右へ追加する余白率（`0.25` = 25%）。 |
| `YOLO_CLASSES` | 検出対象クラスID | `[0]` | 検出対象の COCO クラス ID（`0` = `person`）。カンマ区切りで複数指定できます。 |
| `YOLO_TRACK_ID` | 固定追跡ID | 空欄 (`None`) | 指定した場合のみ、その YOLO 追跡 ID を対象にします。空欄なら動画全体の移動量から主要人物を自動選択します。 |

**RTMPose 骨格推定設定（`POSE_ENGINE = rtmpose` 選択時に表示）**

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `RTMLIB_POSE_MODEL` | RTMPose モデル | `x` | `t` / `s` / `m` / `l` / `x` から選択します。 |
| `RTMLIB_POSE_INPUT_SIZE` | 入力解像度 | `384x288` | `256x192` または `384x288` から選択します。 |
| `BACKEND` | 推論バックエンド | `onnxruntime` | RTMPose の実行バックエンド（`onnxruntime` / `opencv`、`onnxruntime` 推奨）。 |
| `RTMPOSE_BATCH_SIZE` | RTMPose バッチサイズ | `1` | RTMPose で一度に推論するフレーム数（`1`〜`512`）。CPU 実行時・動的バッチ非対応 ONNX モデル・空き VRAM 制限・CUDA OOM 時は自動調整または `1` へフォールバックします。 |
| `KEYPOINT_THRESHOLD` | 関節スコアしきい値 | `0.45` | この値未満の関節は骨格描画や幾何計算で低信頼として扱われます。 |

> **RTMPose の解像度互換性仕様**
> - `t` / `s` / `m`: `256x192` のみ対応
> - `l`: `256x192` または `384x288` に対応
> - `x`: `384x288` のみ対応
> - 非対応の組み合わせを指定した場合、設定画面に警告が出るとともに、解析開始前・保存前チェックでエラーになります。

**ViTPose++ 骨格推定設定（`POSE_ENGINE = vitpose` 選択時に表示）**

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `VITPOSE_MODEL` | ViTPose++ モデルサイズ | `h` | `s`（Small / 最軽量）/ `b`（Base / バランス）/ `l`（Large / 高精度）/ `h`（Huge / 最高精度）から選択します（Hugging Face `usyd-community/vitpose-plus-*`）。 |
| `VITPOSE_INPUT_SIZE` | 解像度 | `256x192` | `256x192`（Classic デコーダ）固定です。 |
| `VITPOSE_BATCH_SIZE` | ViTPose++ バッチサイズ | `4` | 12GB VRAM での OOM 防止のため `1`〜`8` に制限（推奨 `4`）。CPU 時は `1` 固定、空き VRAM による上限調整・CUDA OOM 時の自動半減を行います。 |
| `VITPOSE_FLIP_TEST` | Flip Test（左右反転 TTA） | `true` (`ON`) | 元画像と左右反転画像のヒートマップを平均化し精度・安定性を向上します（`OFF` で推論速度約2倍）。 |
| `KEYPOINT_THRESHOLD` | 関節スコアしきい値 | `0.45` | この値未満の関節は骨格描画や幾何計算で低信頼として扱われます（RTMPose 側と共通キー）。 |

> **ViTPose++ の内部最適化仕様（固定）**
> - Pass 1（YOLO）のモデル破棄・VRAM 解放後にのみ ViTPose++ モデルをロードします（VRAM 競合防止）。
> - CUDA 実行時は **FP16 半精度** で順伝播し、UDP + DARK（Taylor 展開）サブピクセル座標算出の直前に **FP32** へ戻して誤差・ジッターを抑制します。
> - 初回のみ Hugging Face Hub から自動ダウンロードし、2回目以降はローカルキャッシュ（`local_files_only=True`）を優先読み込みします。

### タブ2：トラッキング・重み設定

| グループ | 主な設定キー | 説明 |
| --- | --- | --- |
| トラッカー・対象ロック | `YOLO_TRACKER` (`bytetrack.yaml` / `botsort.yaml`), `TARGET_BOX_FILL_MAX_FRAMES` (`60`), `TARGET_LOCK_RAW_ID` (`true`), `TARGET_REQUIRE_SAME_RAW_ID_WHEN_MISSING` (`true`), `TARGET_SELECTION_MIN_FRAMES` (`15`), `TARGET_SELECTION_COVERAGE_WEIGHT` (`0.5`) | 追跡アルゴリズム、欠損時の線形補間上限、対象人物の自動選択基準および生IDロック条件を設定します。 |
| 再捕捉・距離しきい値 | `TARGET_REACQUIRE_MAX_DISTANCE` (`300.0`), `TARGET_REACQUIRE_MIN_IOU` (`0.05`), `TARGET_TRACK_MATCH_THRESHOLD` (`0.75`), `TARGET_TRACK_MIN_IOU` (`0.15`), `TRACK_MAX_DISTANCE` (`250.0`), `TRACK_MAX_MISSED_FRAMES` (`8`), `TRACK_MATCH_THRESHOLD` (`2.0`) | 見失った後の再捕捉許容範囲とトラック維持のしきい値です。 |
| マッチング・予測重み | `TRACK_CENTER_WEIGHT`, `TRACK_KEYPOINT_WEIGHT`, `TRACK_POSE_WEIGHT`, `TRACK_BBOX_WEIGHT`, `TRACK_VELOCITY_SMOOTHING`, `TRACK_RAW_ID_BONUS`, `TRACK_PREDICTED_BOX_WEIGHT`, `TRACK_PREDICTION_MAX_FRAMES`, `POSE_TRACK_*`, `POSE_BOX_*`, `POSE_TEMPORAL_WEIGHT` | トラックID安定化およびクロップ内での最適人物選択に使う各コスト重みです。 |

### タブ3：可視化・オーバーレイ設定（補足）

- UI上には `可視化・オーバーレイ設定` タブ（`DRAW_SKELETON`, `DRAW_BBOX`, `SKELETON_LINE_WIDTH`, `KEYPOINT_RADIUS`, `LABEL_FONT_SCALE`）が用意されていますが、現在の解析ワーカー（`gui.py`）では描画設定は固定値で動作し、これらUI項目は設定保存用（将来拡張用）となっています。

---

## 6. 出力ファイル・CSV仕様・2段階処理の仕組み

### 6.1 出力ファイル一覧

出力ファイル名は **出力先フォルダーの最下層フォルダ名** を使って自動生成されます。たとえば出力先フォルダー名が `跳躍動画` の場合、同フォルダ内に以下の5ファイルが生成されます。

| ファイル名例 | 内容 |
| --- | --- |
| `跳躍動画.mp4` | 最終的な骨格推定結果の描画動画（対象人物の骨格＋`YOLO stable_id`＋`Frame` 番号入り） |
| `跳躍動画-crop.mp4` | 姿勢推定エンジン推論時に使用される前処理後の人物 crop 画像（骨格なし。RTMPose 時は `288×384` または `192×256`、ViTPose++ 時は `192×256`）の動画 |
| `跳躍動画-crop-skeleton.mp4` | 上記 crop 画像に骨格のみを描画した動画（文字オーバーレイなし。RTMPose 時は `288×384` または `192×256`、ViTPose++ 時は `192×256`） |
| `跳躍動画.csv` | フレームごとの関節座標・信頼度スコア記録（UTF-8 BOM付き） |
| `跳躍動画_metadata.txt` | 元動画のパス、撮影日時（`exiftool` / `ffprobe`）、総フレーム数、解像度、FPS、動画長 |

### 6.2 CSVフォーマット

- 1行に1フレームを記録します（`frame`, `time_seconds` に続いて人物ごとの列が横並び）。
- `person_0_id`、`person_1_id` ...（最大 `CSV_MAX_PERSONS` 人分）を持ち、各人物について COCO 17部位ごとの `_x`、`_y`、`_score` 列が出力されます。
- 17部位: `鼻`, `左目`, `右目`, `左耳`, `右耳`, `左肩`, `右肩`, `左肘`, `右肘`, `左手首`, `右手首`, `左股関節`, `右股関節`, `左膝`, `右膝`, `左足首`, `右足首`
- 人物が検出されなかったフレーム／枠は空欄になります。

### 6.3 2段階処理アーキテクチャ

1. **第1段階（全体追跡）**: 動画全体を YOLO11 + ByteTrack/BoT-SORT で先に処理し（`YOLO_BATCH_SIZE` に応じて複数フレームをバッチ推論）、中心位置・移動速度・バウンディングボックス重なり（IoU）を組み合わせて安定した人物ID（`stable_id`）を付与します。全フレームの軌跡を集計し、指定ID（`YOLO_TRACK_ID`）または動画全体で移動量が大きい人物を対象に決定します（第1段階の動画書き出しは行いません）。また `POSE_ENGINE = vitpose` の場合は、この Pass 1 実行中にバックグラウンドスレッド（`ViTPosePreimport`）で `transformers` ライブラリを事前読み込みし、Pass 2 への切り替え待ちを短縮します。完了時には YOLO モデルと CUDA キャッシュを解放して VRAM を空けます。
2. **第2段階（直接骨格推定）**: 動画を先頭から再度読み込み、第1段階で確定した対象人物の矩形（`target_box`）をもとに選択エンジンの入力仕様へアフィン変換して姿勢推定を行います（`YOLOX` による再検出はスキップします）。
   - **RTMPose 選択時**: ONNX / SimCC モデルへ前処理画像を渡し、`RTMPOSE_BATCH_SIZE > 1` かつ動的バッチ対応 ONNX モデルの場合はバッチ推論します。
   - **ViTPose++ 選択時**: UDP アフィン変換・ImageNet 正規化を行って PyTorch モデル（CUDA 時は FP16）で推論し、Flip Test（有効時）と UDP + DARK（FP32）によるサブピクセル座標復号を行います。
   - 推定結果を元動画へ骨格描画した動画・crop 動画2本（骨格なし／骨格あり、未検出フレームは黒画面でフレーム数一致）・CSV を保存します。OpenCV `mp4v` コーデックのタイムベース分母上限（65535）を超える FPS は自動調整して書き出します。

※ 中間クロップ動画ファイルを読み戻して推論するのではなく、インメモリで推論用画像を作成したついでにそのまま非同期ライターで動画へ書き出します。CPU 実行時・空き VRAM 上限到達時・CUDA OOM 発生時（および RTMPose ONNX が静的バッチ固定の場合）は自動的にバッチサイズを縮小（半減または `1` へフォールバック）して処理を継続します。また GPU 実行時は Windows WDDM の共有メモリ退避によるハングを防ぐため、空き VRAM に応じたプロセス上限（`set_per_process_memory_fraction`）を設定します。

---

## 7. 開発者向け情報（コマンドオプション・UI開発・自動テスト）

### コマンドラインオプション（`gui.py`）

```bash
python gui.py           # 標準起動（PyWebView + ビルド済み frontend/dist を使用）
python gui.py --dev     # Vite 開発サーバー (http://localhost:5173) に接続して起動
python gui.py --debug   # PyWebView デバッグモードを有効にして起動
python gui.py --legacy  # 従来版 CustomTkinter GUI を起動（RTMPose中心の旧設定UIのみ・ViTPose++用UIは未対応）
```

### フロントエンド（React/Vite）の編集・再ビルド

UI（`frontend/src/`）を編集する場合のみ [Node.js](https://nodejs.org/) が必要です。

```bash
cd frontend
npm install
```

- **ホットリロード付きで開発確認する場合**:
  1. ターミナル1: `cd frontend && npm run dev`
  2. ターミナル2（リポジトリルート）: `.\.venv\Scripts\python.exe gui.py --dev`（macOS は `python gui.py --dev`）
- **本番用ビルド（`frontend/dist/`）を更新する場合**:
  ```bash
  cd frontend
  npm run build
  ```
  ※ リポジトリ方針として `frontend/dist/` を Git で管理しているため、UI ソース変更時は `npm run build` の結果もあわせてコミットしてください。

### 自動テストの実行方法

> **注意**: `tests/` ディレクトリは `.gitignore` により Git 管理から除外されています。ローカル環境に `tests/` が配置されている開発環境では、以下のコマンドでユニットテスト／結合テストを実行できます。

**Windows（PowerShell）:**

```powershell
# 全 Python テストの一括実行
.\.venv\Scripts\python.exe -m unittest discover -s tests

# 個別スイート（例: 姿勢推定エンジン / ViTPose++ / PyWebView ブリッジ / バンドル検証 / 自動終了ウィンドウ起動テスト）
.\.venv\Scripts\python.exe -m unittest tests/test_pose_estimators.py
.\.venv\Scripts\python.exe -m unittest tests/test_api_bridge_vitpose.py
.\.venv\Scripts\python.exe -m unittest tests/test_pywebview_migration.py
.\.venv\Scripts\python.exe -m unittest tests/test_m3_bundle_and_build.py
.\.venv\Scripts\python.exe -m unittest tests/test_pywebview_window_launch.py

# Node.js テスト（組み込み node:test ランナー）
node --test tests/test_event_deduplicator_adversarial.mjs tests/test_frontend_stress_m3.mjs tests/test_pywebview_telemetry_integration.mjs
```

**macOS（仮想環境有効化後）:**

```bash
python -m unittest discover -s tests
node --test tests/*.mjs
```

---

## 8. トラブルシューティング

- **「フロントエンドのビルドが必要です (`frontend/dist/index.html` が検出されませんでした)」と表示される**
  - `frontend/dist/` が削除されているか、古い状態で取得されています。Node.js 導入後に `cd frontend && npm install && npm run build` を実行してください。一時的に旧UIで動かしたい場合は `python gui.py --legacy` も使えます。
- **Windows で起動しても画面が開かない・WebView 関連エラーが出る**
  - Windows 10 等で Microsoft Edge WebView2 ランタイムが未導入の可能性があります。[Microsoft Edge WebView2 公式](https://developer.microsoft.com/ja-jp/microsoft-edge/webview2/) からランタイムを導入してください。
- **NVIDIA GPU を積んでいるのに `実行デバイス: CPU` と表示される**
  - `requirements.txt` を後から実行した等で CPU版 `onnxruntime` が混入している可能性があります。[3.5 GPU環境とCPU環境についての補足・切り替え](#35-gpu環境とcpu環境についての補足切り替え) の再導入手順を実行してください。また NVIDIA ドライバーが古すぎないか（CUDA 13.0 対応か）もご確認ください。
- **macOS で `rtmlib起動.command` をダブルクリックしても開けない**
  - `chmod +x rtmlib起動.command` を実行した後、Finder 上で **右クリック（Control＋クリック）→「開く」** を試してください。
- **macOS で `--legacy` 起動時に Tkinter エラーが出る**
  - Homebrew 版 Python 等で `tkinter` が入っていない場合は `brew install python-tk`（使用中の Python バージョンに合わせて `python-tk@3.14` 等）または [Python 公式インストーラー](https://www.python.org/downloads/) を使用してください（標準の PyWebView UI には Tkinter は不要です）。
- **`_metadata.txt` の撮影日時が「取得不可」になる**
  - `exiftool` または `ffprobe` が未導入（または PATH が通っていない）状態です。[2.3 任意ツール](#23-任意ツール撮影日時の取得用) を参照してインストールしてください。
- **ViTPose++ 初回実行時にモデル読み込みが進まない／エラーになる**
  - 未ダウンロードのサイズ（`s` / `b` / `l` / `h`）を初めて使う場合のみ Hugging Face Hub への接続が必要です（ログに `初回モデルダウンロード中: usyd-community/vitpose-plus-...` が表示されます）。一度ダウンロードが完了すれば 2回目以降はローカルキャッシュからオフライン動作します。また既存の `.venv` で `transformers` が入っていない場合は `python -m pip install "transformers>=4.49.0"` を実行してください。
