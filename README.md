# 動画姿勢推定アプリ（YOLO11 + ByteTrack + RTMPose / ViTPose++）

動画から人物を検出・追跡し、主要人物1名の17関節キーポイント（COCO形式）を推定して、骨格動画・姿勢推論用crop動画2本（骨格なし／骨格あり）・CSVデータ・NPZデータ・動画メタデータ（TXT / JSON）の計7ファイルを出力するデスクトップアプリケーションです。
姿勢推定エンジンは高速・省メモリな **RTMPose（RTMLib / ONNX Runtime）** と、研究向け高精度な **ViTPose++（ONNX Runtime / PyTorch / Hugging Face Transformers）** を切り替えられます。
デスクトップUIは **PyWebView + React/Vite** で構成されており、複数動画の予約登録・連続自動解析・中断/再開・パラメータ検索・ドラッグ＆ドロップに加えて、**ローカル PC 実行と Google Colab GPU ハイブリッド実行（`CLI + SSH直結` / `手動URL`）の切り替え** に対応しています。

---

## 目次

- [1. 動作環境と対応構成](#1-動作環境と対応構成)
- [2. 新規パソコンでの事前準備（ダウンロード・リンク一覧）](#2-新規パソコンでの事前準備ダウンロードリンク一覧)
  - [2.1 必須ソフトウェア](#21-必須ソフトウェア)
  - [2.2 OS・実行環境別の追加ソフトウェア](#22-os実行環境別の追加ソフトウェア)
  - [2.3 Google Colab ハイブリッド実行を使う場合（任意・高速GPU推論）](#23-google-colab-ハイブリッド実行を使う場合任意高速gpu推論)
  - [2.4 開発者向けツール（UIを編集・再ビルドする場合のみ）](#24-開発者向けツールuiを編集再ビルドする場合のみ)
- [3. 初期構築からアプリ起動までの手順](#3-初期構築からアプリ起動までの手順)
  - [3.1 リポジトリの取得](#31-リポジトリの取得)
  - [3.2 Windows（NVIDIA GPU版・推奨・高速）](#32-windowsnvidia-gpu版推奨高速)
  - [3.3 Windows（CPU版）](#33-windowscpu版)
  - [3.4 macOS（CPU版）](#34-macoscpu版)
  - [3.5 GPU環境とCPU環境についての補足・切り替え](#35-gpu環境とcpu環境についての補足切り替え)
- [4. Google Colab GPU ハイブリッド実行の使い方](#4-google-colab-gpu-ハイブリッド実行の使い方)
  - [4.1 ハイブリッド処理の仕組み](#41-ハイブリッド処理の仕組み)
  - [4.2 方法①：SSH直結（自動・推奨）モード（Windows）](#42-方法ssh直結自動推奨モードwindows)
  - [4.3 方法②：手動URL（従来ノートブック）モード](#43-方法手動url従来ノートブックモード)
  - [4.4 自動停止・複数PCでの持ち替え・キャッシュの挙動](#44-自動停止複数pcでの持ち替えキャッシュの挙動)
- [5. アプリの使い方（GUI操作ガイド）](#5-アプリの使い方gui操作ガイド)
  - [5.1 画面構成](#51-画面構成)
  - [5.2 基本の流れ（予約〜連続解析）](#52-基本の流れ予約連続解析)
  - [5.3 中断・失敗・重複回避・自動保存の仕様](#53-中断失敗重複回避自動保存の仕様)
  - [5.4 実行ログ・進捗バー・デバイスの挙動](#54-実行ログ進捗バーデバイスの挙動)
- [6. 設定項目の説明](#6-設定項目の説明)
- [7. 出力ファイル・CSV/NPZ仕様・2段階処理の仕組み](#7-出力ファイルcsvnpz仕様2段階処理の仕組み)
  - [7.1 出力ファイル一覧](#71-出力ファイル一覧)
  - [7.2 CSV / NPZ フォーマット](#72-csv--npz-フォーマット)
  - [7.3 2段階処理アーキテクチャ](#73-2段階処理アーキテクチャ)
- [8. 開発者向け情報（コマンドオプション・UI開発・自動テスト）](#8-開発者向け情報コマンドオプションui開発自動テスト)
- [9. トラブルシューティング](#9-トラブルシューティング)

---

## 1. 動作環境と対応構成

| OS / 環境 | 対応実行モード | 使用する依存定義 | 起動方法 |
| --- | --- | --- | --- |
| **Windows 10 / 11** | **NVIDIA GPU (CUDA 13.0)** / **Colab GPU** | `requirements-gpu.txt` + `rtmlib` (`--no-deps`) | `rtmlib起動.cmd` または `.\.venv\Scripts\python.exe gui.py` |
| **Windows 10 / 11** | **CPU** / **Colab GPU** | `requirements.txt` | `rtmlib起動.cmd` または `.\.venv\Scripts\python.exe gui.py` |
| **macOS** (Apple Silicon / Intel) | **CPU** / **Colab GPU (手動URL)** | `requirements.txt` | `rtmlib起動.command` または `python gui.py` |

> **macOS および非GPU PC での実行について**
> - ローカル推論の `DEVICE` 設定は `auto` / `cpu` / `cuda` に対応しており、NVIDIA CUDA 非対応環境では `auto`（初期値）で自動的に CPU 実行になります。
> - ローカルに高速な GPU がない環境でも、後述の **Google Colab GPU ハイブリッド実行** を使えばクラウド上の GPU（T4 / L4 / A100 等）で推論を行えます。

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
> YOLO11 の重みファイル（`yolo11*.pt`）、RTMPose のモデル（ONNX zip）、および ViTPose++ のモデル（Hugging Face Hub の `usyd-community/vitpose-plus-*`）は Git には含まれていません。**各モデルの初回解析実行時に自動的にダウンロード** されるため、初回実行時はインターネットに接続した状態で行ってください。
> なお、ViTPose++ は初回ロード時に ONNX 形式へ変換してローカルキャッシュ（`VITPOSE_ONNX_CACHE_DIR`）に保存し、Hugging Face キャッシュも 2 回目以降はオフライン優先読み込み（`local_files_only=True`）するため、次回以降高速に起動します。

### 2.2 OS・実行環境別の追加ソフトウェア

| 対象 | 項目 | ダウンロード先・備考 |
| --- | --- | --- |
| **Windows (NVIDIA GPU版)** | **NVIDIA グラフィックスドライバー** | [NVIDIA ドライバーダウンロード](https://www.nvidia.com/ja-jp/drivers/)<br>CUDA 13.0 に対応する最新の公式ドライバーをインストールしてください。PyTorch に CUDA / cuDNN が同梱されており ONNX Runtime からも読み込むため、**CUDA Toolkit の別途インストールは不要**です。 |
| **Windows 10 等** | **Microsoft Edge WebView2 ランタイム** | [Edge WebView2 公式ページ](https://developer.microsoft.com/ja-jp/microsoft-edge/webview2/)（ページ内の「エバーグリーン スタンドアロン インストーラー」等）<br>Windows 11 は標準搭載のため通常不要です。Windows 10 でアプリウィンドウが開かない場合のみ導入してください。 |
| **macOS** | **Xcode Command Line Tools**（必要時のみ） | ターミナルで `xcode-select --install`<br>`pip install` 時にビルドが必要になった場合や `git` コマンドを使う場合のみ導入します。 |

### 2.3 Google Colab ハイブリッド実行を使う場合（任意・高速GPU推論）

- **手動URL（従来ノートブック）モード** を使う場合：Google アカウント（ブラウザ）のみで利用できます。
- **SSH直結（自動・推奨）モード（Windows）** を使う場合：以下を使用します（初回はアプリ内の「Colab 接続設定」モーダルからガイド・自動実行できます）。
  - **`uv`**（`google-colab-cli` の導入用。未導入時は [uv 公式手順](https://docs.astral.sh/uv/getting-started/installation/) で導入後、GUI 上のボタンから `google-colab-cli` を導入可能）
  - **Windows OpenSSH クライアント**（Windows 10/11 は通常標準搭載。SSH 鍵 `~/.ssh/id_ed25519` はアプリ内ボタンで自動生成可能）
  - **Google アカウント**（Colab 無料枠または Colab Pro / Compute Units）

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

NVIDIA 製 GPU を搭載していない Windows PC（または Colab 実行専用の PC）の場合は、PowerShell で以下を実行します。

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

- GPU用の構成は **PyTorch 2.14.1 / torchvision 0.29.1（CUDA 13.0版）**・**ONNX Runtime GPU 1.31.1**・**Transformers 4.49.0以上（ViTPose++ 用）** です。実行時に PyTorch に含まれる CUDA・cuDNN DLL を `onnxruntime-gpu` にも読み込ませるため（[pose_estimators/base.py](pose_estimators/base.py)）、CUDA Toolkit の別途インストールは不要です。
- `rtmlib==0.0.16` はパッケージの依存情報に CPU版の `onnxruntime` を指定しています。CPU版 `onnxruntime` と GPU版 `onnxruntime-gpu` は同じ Python モジュール名（`onnxruntime`）を上書き共有するため、同時に導入すると GPU 推論が壊れます。
- そのため GPU 環境では、必要な依存（`opencv-contrib-python`・`numpy`・`tqdm`・`transformers` 等）を含めた `requirements-gpu.txt` を先に入れ、`rtmlib==0.0.16` のみ `--no-deps` で導入する手順としています。
- この構成では `pip check` が「`rtmlib` に `onnxruntime` が不足している」と報告することがありますが、実行時には `onnxruntime-gpu` がその機能を提供するため正常動作します。

#### 既存の CPU 環境から GPU 環境へ切り替える場合（Windows）

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y onnxruntime
.\.venv\Scripts\python.exe -m pip install --force-reinstall -r requirements-gpu.txt
.\.venv\Scripts\python.exe -m pip install --no-deps rtmlib==0.0.16
```

#### GPU環境を維持したままパッケージを追加・更新する場合

既に動作中の旧 GPU 環境（`.venv`）をアップデートする場合は、`requirements.txt` を再実行せず不足パッケージだけを追加してください（`requirements.txt` を実行すると CPU版 `onnxruntime` が再導入されてしまいます）：

```powershell
.\.venv\Scripts\python.exe -m pip install "pywebview>=6.0" "transformers>=4.49.0" "onnx>=1.16"
```

詳細は [PyTorch公式](https://pytorch.org/get-started/previous-versions/) および [ONNX Runtime公式（CUDA Execution Provider）](https://onnxruntime.ai/docs/execution-providers/CUDA-Execution-Provider.html) を参照してください。

---

## 4. Google Colab GPU ハイブリッド実行の使い方

### 4.1 ハイブリッド処理の仕組み

上部アクションバーで実行先を **`Colab GPU`** に切り替えると、以下のようにローカル PC と Google Colab の GPU で負荷を分担します：

1. **Colab GPU 側（`colab_server`）**:
   - 動画をチャンクアップロード（同一動画の SHA-256 が Colab 上にキャッシュ済みならアップロードをスキップし、次の予約動画を最大 5 本まで裏で先読みアップロード）。
   - 常駐ワーカー（`gui.py --persistent-worker`）上で Pass 1（YOLO + ByteTrack）と Pass 2（RTMPose / ViTPose++）を `data_only` モードで実行し、CSV・NPZ・メタデータのみを生成して ZIP で返却します。
2. **ローカル PC 側**:
   - 受信した NPZ / CSV データと手元の元動画を使い、**3 本の MP4 動画（骨格動画・crop 動画 2 本）を裏の並列スレッドでレンダリング** します。その間に Colab GPU 側は次の動画の推論を進めます。

Colab への接続には **「SSH直結（自動・推奨）」** と **「手動URL（従来ノートブック）」** の 2 方式があり、「Colab 接続設定」モーダル内のタブでいつでも切り替えられます（`手動URL` 側の設定も独立して保持されます）。

---

### 4.2 方法①：SSH直結（自動・推奨）モード（Windows）

ブラウザでノートブックを開いたり、`trycloudflare.com` URL やトークンを毎回コピペしたりせずに、**ローカルアプリ上の操作だけで Colab GPU ランタイムの割り当て・サーバー起動・SSH ポート転送まで自動完結するモード** です（デフォルト設定）。

#### 初回セットアップ（PC ごとに 1 回のみ）

上部バーの **`Colab GPU`** または横の接続設定ボタン（`Colab SSH: 待機 (...)`）をクリックして **「Google Colab 接続設定」モーダル** を開くと、**「PC セットアップ状況」** カードが表示されます。すべて PowerShell を開かずにモーダル内から準備できます：

1. **Colab CLI (`google-colab-cli`)**: 未導入の場合、`uv` が入っていれば **「`uv` で自動インストール」** ボタンで導入できます（`uv` 自体が無い場合は PowerShell 等で `uv` を入れて「再確認」を押してください）。
2. **SSH 鍵 (`ed25519`)**: 未作成の場合、**「SSH 鍵を自動生成」** ボタンで `~/.ssh/id_ed25519` を作成します。
3. **Google 認証**: 未認証の場合、**「Google 認証を開始」** を押すと認証用 URL が表示されます。ブラウザで開いて Google アカウントを許可し、画面に出た認証コードをモーダル内の入力欄に貼り付けて **「認証コード送信」** を押します（完了後は残高 Compute Units も表示されます）。

#### ランタイム設定と実行

- **使用 GPU アクセラレータ**: `T4`（標準・安定）/ `L4`（High-RAM固定）/ `A100` / `G4` / `H100` から選択します。
  - 利用可否と消費レートは契約中の Google Colab プラン・空き枠に依存します。割り当て拒否や上限エラーが出た場合は、エラーカード内の **「`T4` に切り替えて再試行」** ボタンから即切り替えられます。
- **High-RAM ランタイム (`--high-mem`)**: メモリ拡張が必要な場合にチェックします（`L4` は単一構成のみのため自動で無効化されます）。
- **Google Drive モデルキャッシュ同期**: **既定 OFF**。OFF でも同じモデルキャッシュ（`/content/.cache`）を使って問題なく推論できます。ON 時に Google Drive 側の認証・マウントエラーが発生した場合でも処理は止まらず、警告表示のうえで自動的にローカルキャッシュ（`/content/.cache`）のみで続行します。
- **無操作時の自動停止（分）**: **既定 30 分**（`0` で無効）。

**起動と実行方法：**
- 準備ができていれば、そのままメイン画面の **`▶ 解析開始`** を押すだけで裏側から自動起動（新規割り当て → 必要最小 12 ファイルのコード転送 → パッケージ導入 → SSH ポート転送確立）して解析が始まります。
- 解析前に GPU の状態を確認したい場合は、モーダル内の **「今すぐ起動・接続」** ボタンで手動起動もできます。

---

### 4.3 方法②：手動URL（従来ノートブック）モード

複数台の PC から 1 つの Colab サーバーへ接続したい場合や、ブラウザから直接 Colab を操作したい場合（macOS を含む）は、モーダル内の **`手動URL（従来ノートブック）`** タブに切り替えます。

1. Google Colab で本リポジトリの [colab/launch_colab_server.ipynb](colab/launch_colab_server.ipynb) を開き、メニュー「ランタイム」→「ランタイムのタイプを変更」から GPU（`T4` / `L4` / `A100`）を選択します。
2. **セル 1** で必要に応じて設定を確認し（Colab 側で Drive マウント障害が起きている場合やキャッシュ不要な場合は `USE_DRIVE_CACHE` のチェックを外してください）、**セル 1〜4** を上から順に実行します。
3. セル 4 に表示される **サーバー URL（`https://....trycloudflare.com`）** と **API トークン** をコピーし、アプリ側の「Colab 接続設定」→ `手動URL` タブに貼り付けて **「接続テスト (/health)」** → **「保存して反映」** を押します。
4. 上部バーで `▶ 解析開始` を押すと Colab サーバーへジョブが送信されます。終了時は Colab 側のセル 4 停止ボタンでサーバーを止めてください。

---

### 4.4 自動停止・複数PCでの持ち替え・キャッシュの挙動

- **切り忘れ防止の自動停止（SSH直結モード）**:
  - **無操作自動停止（ローカル側）**: 実際に解析が動いていない完全待機状態が設定時間（既定 30 分）続くと、自動で `colab stop` を実行してランタイムを解放します（※ 予約一覧に未開始の予約動画が残っていても、実行中でなければ自動停止します）。上部バーのバッジに残り時間の目安が表示され、横の停止アイコンやモーダル内の「ランタイムを停止」でいつでも即停止できます。
  - **アプリ終了時の自動停止**: アプリウィンドウを閉じると SSH トンネルと実行中セッションを自動停止します。
  - **強制スリープ・クラッシュ時のリモート側ウォッチドッグ**: PC がスリープ・強制終了してローカルから停止命令を送れなかった場合も、Colab サーバー側（[colab_server/app.py](colab_server/app.py)）がローカルからの通信途絶を 30 分検知すると GPU ワーカーを終了して自己停止します。
- **家・研究室など複数 PC で切り替えて使う場合（SSH直結モード）**:
  - 使う PC ごとに上記の「初回セットアップ（CLI / SSH 鍵 / Google 認証）」を 1 回行えば、同じ Google アカウントで切り替え運用できます。
  - 同じ PC でアプリを再起動した際、同条件のセッションがまだ生きていれば SSH トンネルやサーバーだけを再接続して再利用します（トンネル単体落ち時はまずトンネル再接続のみ、必要に応じて同一 VM 上でサーバー再起動する 2 段階復旧）。
  - 別の PC で止め忘れたセッションが残っている場合は一覧上 `[?]` として検出され警告を表示します。上限枠に引っかかった場合はブラウザ上の Google Colab「ランタイム → セッションを管理」から不要セッションを終了してください。

---

## 5. アプリの使い方（GUI操作ガイド）

### 5.1 画面構成

アプリを起動すると、上部バー＋左右2ペインの画面が開きます。

1. **上部アクションバー**
   - **`▶ 解析開始`**: 予約リストの先頭にある待機動画から順番に自動解析を開始します（Colab `SSH直結` モード時に未起動なら自動で起動・接続してから開始します）。
   - **`■ 解析中断`**: 現在実行中の解析プロセスを停止し、その動画を予約リストの先頭（待機中）へ戻します。
   - **実行先トグル（`ローカル` / `Colab GPU`）** ＆ **Colab 設定・状態ピル**（稼働状態・GPU名・自動停止までの残り時間表示、稼働中のクイック停止ボタン付き）。
   - 右側のステータスバナーに現在の状態・進捗率が表示されます。
2. **左ペイン（解析中モニター）** — 設定画面などを開いている間も常に表示されます。
   - ステータスバッジ（`待機中` / `解析実行中` / `YOLO 処理中` / `RTMPose 処理中` / `ViTPose++ 処理中` / `中断処理中`）
   - 16:9 動画プレビュー・動画名・出力フォルダー名・解像度
   - 円形進捗バー（0〜50%: YOLO 人物検出・追跡 / 50〜100%: 選択した姿勢推定エンジン）
   - 実行ログ欄（一時停止・クリアボタン付き）
3. **右ペイン（ワークスペース）** — 以下の3画面を切り替えて操作します。
   - **`予約リスト`**: 登録済みの動画カード一覧（各カードに姿勢推定モデル・YOLOサイズ・デバイス、Colab利用時はローカルMP4書き出し中表示）、`削除`・`上へ`・`下へ`・`基本設定` ツールバー、点線枠 `＋ 予約を追加`
   - **`予約を追加`**: 動画選択・出力先指定・出力7ファイルプレビュー・適用される初期設定サマリー表示
   - **`基本設定` / 個別 `設定`**: 検索バー＋3つの設定タブ（検索バー入力時は3タブの全項目を1画面に展開表示）

### 5.2 基本の流れ（予約〜連続解析）

1. **既定の出力先や初期条件を設定する（初回推奨）**
   - 予約リスト右上の **`基本設定`** をクリックし、「新規予約時の既定出力親フォルダー」や実行デバイス・モデル等の初期条件を確認し、**`基本設定を保存`** を押します（`gui_settings.json` に保存され、次回起動時にも読み込まれます）。
2. **（Colab を使う場合）上部バーで実行先を `Colab GPU` に切り替える**
   - `SSH直結` モードで初回セットアップが未完了の PC では自動で設定モーダルが開きます。
3. **解析したい動画を予約に追加する**
   - 点線枠 **`＋ 予約を追加`** をクリックする（または点線枠へ動画ファイルをドラッグ＆ドロップする）と追加画面が開きます。
   - **`動画ファイルを選択…`**（または枠内へのドロップ）で動画を1本または複数本選択します。
   - **1本選択時**: 出力先フォルダー名を直接指定でき、生成される 7 つのファイル名プレビューが表示されます。
   - **複数本選択時**: 出力親フォルダーを指定すると、その配下に動画ごとのサブフォルダーが自動作成されます。
   - **`予約リストに追加する`** を押すと予約リストに登録されます。
4. **順番・個別設定を調整する**
   - 予約リストの各行をクリックして選択（`Ctrl` / `Shift` での複数選択も可）し、**`上へ` / `下へ`** またはカードのドラッグ＆ドロップで実行順を並べ替え、**`削除`** で不要な予約を外せます（元動画や出力済みファイルは削除しません）。
   - 待機中または失敗した動画は、各カードの **`設定`** ボタンから予約追加後でも出力先やモデル・追跡条件を個別に編集できます（`基本設定を反映` ボタンで現在の基本設定を読み込むこともできます）。
5. **解析を開始する**
   - 上部バーの **`▶ 解析開始`** を押すと、待機中の予約を上から順に自動実行します。
   - 解析実行中でも、右ペインで新しい予約の追加や未実行予約の編集を行えます。

### 5.3 中断・失敗・重複回避・自動保存の仕様

- **完了後の表示**: 正常に解析が完了した動画は予約リストから自動で非表示になります（出力先フォルダーの解析結果はそのまま保持されます）。
- **失敗時の再実行**: エラーで失敗した動画は赤いカードで予約リストに残り、エラー要旨の確認、**`設定`** からの条件見直し、**`再試行`** ボタンでの再待機化が行えます。
- **中断と再開**: **`■ 解析中断`** を押す（または解析中にアプリを閉じる）と実行中のプロセス／リモートジョブを停止し、その動画を待機中の先頭へ戻します。再実行時はその動画の先頭からやり直します。
- **フォルダ重複の自動回避**: 出力先フォルダーが既に存在する場合（中断後の再実行や同名動画など）は、既存結果を上書きしないよう `_2`、`_3` のように連番付きフォルダーへ自動変更して保存します。
- **状態と設定の自動保存**:
  - 基本設定は `gui_settings.json`、Colab 接続設定は `.colab_config.json` に保存されます。
  - 予約一覧・登録順・状態・個別設定は `analysis_queue.json` に自動保存され、次回起動時に復元されます（前回解析中だった予約も自動で待機中の先頭へ戻ります）。
  - 実行時の設定スナップショットは `.analysis_jobs/configs/`、予約ごとの詳細ログは `.analysis_jobs/logs/` に保存されます（いずれも `.gitignore` 対象）。

### 5.4 実行ログ・進捗バー・デバイスの挙動

- **実行デバイス（`DEVICE`）の挙動**:
  - `auto`（初期値）: `POSE_ENGINE = rtmpose` の場合は PyTorch CUDA と ONNX Runtime CUDA（`CUDAExecutionProvider`）が両方使える場合に GPU を選択し、`POSE_ENGINE = vitpose` の場合は ONNX Runtime CUDA または PyTorch CUDA が使える場合に GPU を選択します。GPU 環境が不足している場合は、理由をログに表示して自動的に CPU を選択します。
  - `cuda`: 両方の推論（YOLO + 姿勢推定モデル）を GPU で実行します。GPU 環境が不足している場合はエラーで停止します。
  - `cpu`: 両方の推論を CPU で実行します。
  - 実行ログには、`実行デバイス: CUDA:0 (<GPU名>)`（または `CPU`）、`姿勢モデル: RTMPose-...` / `ViTPose++-...`、各段階の実行バッチサイズ（VRAM 空き容量による自動制限・OOM 発生時の自動半減フォールバックを含む）、および `mp4v` 制限に伴う FPS 調整時（`動画書き出しFPS調整`）のメッセージを表示します。なお動画のデコード・エンコードや追跡処理などは引き続き CPU も使用します。
- **進捗バー**:
  - `0〜50%`: YOLO 処理（動画情報の総フレーム数を使った概算です。動画ヘッダ情報と実際に読み込めるフレーム数が異なる場合、完了時に 50% へ飛ぶことがあります）。
  - `50〜100%`: 姿勢推定処理（RTMPose / ViTPose++。YOLO 終了時にログへ表示する「実処理フレーム数」を基準に計算します）。
- **分析速度ログ**:
  - 解析完了時のログに、YOLO と選択した姿勢推定エンジンそれぞれの分析時間（秒）と分析速度（フレーム/秒）を小数点以下2桁で表示します。分析時間にはモデル初期化・動画読み込み・描画・結果保存を含みます。

---

## 6. 設定項目の説明

設定画面（`基本設定`／個別 `設定`）には上部検索バー（キーワード入力時は3タブの全項目を1画面に展開表示）と3つのタブがあります。

### タブ1：基本・出力設定

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `POSE_ENGINE` | 姿勢推定エンジン | `rtmpose` | `RTMPose`（高速・省メモリ / ONNX）または `ViTPose++`（研究用・最高精度 / ONNX & PyTorch）から選択します。非選択側の設定も保持されます。 |
| `DEVICE` | 推論実行デバイス | `auto` | `auto`（自動判定）/ `cpu` / `cuda` から選択します。 |
| `CAPTURE_FPS` | 元動画の撮影フレームレート (FPS) | 空欄 (`None`) | スローモーション再生動画などで実際の撮影 FPS（例: `240`, `119.88`）を指定します。空欄時は動画メタデータ（`exiftool` / `ffprobe`）→ コンテナ再生 FPS の順に自動取得します。 |

**YOLO 検出・しきい値設定**

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `YOLO_MODEL` | YOLOモデル | `yolo11m.pt` | `n`（最速）〜 `x`（最高精度）を選択します。初回実行時に自動ダウンロードされます。 |
| `YOLO_BATCH_SIZE` | YOLO バッチサイズ | `1` | YOLO11 で一度に推論するフレーム数（`1`〜`512`）。CPU 実行時は `1` に固定され、空き VRAM 容量による自動調整・CUDA メモリ不足（OOM）時の半減フォールバックを行います。 |
| `YOLO_IMAGE_SIZE` | YOLO 入力解像度 | `1280` | YOLO の入力解像度（`320`〜`2560` px, 32刻み）。大きいほど小さい人物・遠景を検出しやすくなりますが処理時間が増えます。 |
| `YOLO_CONFIDENCE` | YOLO 検出信頼度 | `0.20` | YOLO の人物検出信頼度しきい値（`0.01`〜`1.0`）。 |
| `YOLO_IOU` | YOLO NMS IoU しきい値 | `0.50` | YOLO の NMS IoU しきい値。重複ボックスの除外基準です。 |
| `YOLO_CLASSES` | 検出対象クラスID | `[0]` | 検出対象の COCO クラス ID（`0` = `person`）。カンマ区切りで複数指定できます。 |

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
| `VITPOSE_PRECISION` | 計算精度 (CUDA) | `fp16` | CUDA 実行時の精度を `fp16`（半精度・高速省VRAM）または `fp32`（単精度・高精度）から選択します。CPU 時は自動で `fp32` になります。 |
| `VITPOSE_FLIP_TEST` | Flip Test（左右反転 TTA） | `true` (`ON`) | 元画像と左右反転画像のヒートマップを平均化し精度・安定性を向上します（`OFF` で推論速度約2倍）。 |
| `VITPOSE_BATCH_SIZE` | ViTPose++ バッチサイズ | `4` | `1`〜`64` の範囲で指定します（空き VRAM による上限調整・CUDA OOM 時の自動半減、CPU 時は `1` 固定）。 |
| `KEYPOINT_THRESHOLD` | 関節スコアしきい値 | `0.45` | この値未満の関節は骨格描画や幾何計算で低信頼として扱われます（RTMPose 側と共通キー）。 |

> **ViTPose++ の内部最適化仕様（固定）**
> - Pass 1（YOLO）のモデル破棄・VRAM 解放後にのみ ViTPose++ をロードします（VRAM 競合防止）。
> - 初回のみ Hugging Face Hub からチェックポイントを取得し ONNX 形式へ自動エクスポートしてキャッシュします（以降はローカル ONNX / キャッシュを優先利用）。
> - CUDA 実行時は指定精度（`fp16` / `fp32`）で推論し、UDP + DARK（Taylor 展開）サブピクセル座標算出の直前に **FP32** へ戻して誤差・ジッターを抑制します。

### タブ2：トラッキング・重み設定

| グループ | 設定キー（初期値） | 説明 |
| --- | --- | --- |
| トラッカー・主要被写体選択 | `YOLO_TRACKER` (`bytetrack.yaml`), `TARGET_BOX_FILL_MAX_FRAMES` (`60`), `TARGET_SELECTION_MIN_FRAMES` (`15`), `TARGET_SELECTION_COVERAGE_WEIGHT` (`0.5`) | 追跡アルゴリズム、対象消失時の線形補間上限フレーム数、主要被写体として自動選定される最低フレーム数と出現割合重みを設定します。 |
| トラック安定化・予測重み | `TRACK_MAX_MISSED_FRAMES` (`8`), `TRACK_MATCH_THRESHOLD` (`2.0`), `TRACK_VELOCITY_SMOOTHING` (`0.35`), `TRACK_RAW_ID_BONUS` (`2.0`), `TRACK_PREDICTED_BOX_WEIGHT` (`0.35`), `TRACK_PREDICTION_MAX_FRAMES` (`2`) | 消失許容フレーム数、マッチング許容コスト、速度平滑化係数、生ID一致ボーナス、移動予測ボックスのIoUコスト重みおよび先読み上限フレームを設定します。 |

### タブ3：可視化・オーバーレイ設定

| 設定キー | UI表示名 | 初期値 | 説明 |
| --- | --- | --- | --- |
| `SKELETON_LINE_WIDTH` | 骨格ライン線幅 | `2` px | 骨格ボーン描画の太さ（`1`〜`8` px）。crop 動画側はクロップサイズに応じて比例スケーリングされます。 |
| `KEYPOINT_RADIUS` | 関節点サークル半径 | `4` px | 各関節キーポイント円の半径（`1`〜`12` px）。 |
| `LABEL_FONT_SCALE` | ラベル文字倍率 | `1.0` | 元動画上のフレーム番号（`Frame: ...`）のフォント倍率（`0.3`〜`2.0`）。 |

---

## 7. 出力ファイル・CSV/NPZ仕様・2段階処理の仕組み

### 7.1 出力ファイル一覧

出力ファイル名は **出力先フォルダーの最下層フォルダ名** を使って自動生成されます。たとえば出力先フォルダー名が `跳躍動画` の場合、同フォルダ内に以下の 7 ファイルが生成されます。

| ファイル名例 | 内容 |
| --- | --- |
| `跳躍動画.mp4` | 最終的な骨格推定結果の描画動画（対象人物の骨格＋`Frame` 番号入り） |
| `跳躍動画-crop.mp4` | 姿勢推定エンジン推論時に使用される前処理後の人物 crop 画像（骨格なし。RTMPose 時は `288×384` または `192×256`、ViTPose++ 時は `192×256`）の動画 |
| `跳躍動画-crop-skeleton.mp4` | 上記 crop 画像に骨格のみを描画した動画（文字オーバーレイなし） |
| `跳躍動画.csv` | フレームごとの主要人物の関節座標・信頼度スコア記録（UTF-8 BOM付き） |
| `跳躍動画.npz` | フレーム番号・時刻・2Dキーポイント・信頼度・追跡枠・クロップパラメータ一式を圧縮保存した NumPy 配列データ（ローカル再描画・Python解析向け） |
| `跳躍動画_metadata.txt` | 元動画パス、確定実フレーム数、解像度、実撮影FPS・再生FPS、VFR検知、実時間、使用AIモデル、対象トラッキングID 等 |
| `跳躍動画_metadata.json` | 上記メタデータの構造化 JSON（スキーマバージョン `1.0`） |

### 7.2 CSV / NPZ フォーマット

- **CSV（`*.csv`）**:
  - 1行に1フレームを記録します（`frame`, `time_seconds`, `person_0_id` に続いて主要人物 1 名の COCO 17 部位ごとの `person_0_{部位}_x`, `person_0_{部位}_y`, `person_0_{部位}_score` 列）。
  - `time_seconds` は `CAPTURE_FPS`（手動指定 → メタデータ自動取得 → 再生 FPS フォールバック）を基準に計算されます。
  - 17部位: `鼻`, `左目`, `右目`, `左耳`, `右耳`, `左肩`, `右肩`, `左肘`, `右肘`, `左手首`, `右手首`, `左股関節`, `右股関節`, `左膝`, `右膝`, `左足首`, `右足首`
  - 人物が検出されなかったフレームは空欄になります。
- **NPZ（`*.npz`）**:
  - `frame_indices`, `timestamps_sec`, `keypoints_xy`, `keypoints_score`, `target_boxes`, `box_state`, `crop_centers`, `crop_scales`, `crop_size`, `crop_keypoints_xy` を格納します。Colab ハイブリッド実行時は Colab 側が出力した NPZ 等をローカルへダウンロードして 3 本の MP4 を生成します。

### 7.3 2段階処理アーキテクチャ

1. **第1段階（全体追跡）**: 動画全体を YOLO11 + ByteTrack/BoT-SORT で先に処理し（`YOLO_BATCH_SIZE` に応じて複数フレームをバッチ推論）、中心位置・移動速度・バウンディングボックス重なり（IoU）を組み合わせて安定した人物ID（`stable_id`）を付与します。全フレームの軌跡を集計し、動画全体の移動量・出現割合から主要人物 1 名を自動決定して欠損フレームを線形補間します。また `POSE_ENGINE = vitpose` で ONNX 未キャッシュの場合は、この Pass 1 実行中にバックグラウンドスレッドで `transformers` 等を事前読み込みします。完了時には YOLO モデルと CUDA キャッシュを解放して VRAM を空けます。
2. **第2段階（直接骨格推定）**: 動画を先頭から再度読み込み、第1段階で確定した対象人物の矩形（`target_box`）をもとに選択エンジンの入力仕様へアフィン変換して姿勢推定を行います（`YOLOX` による再検出はスキップします）。
   - **RTMPose 選択時**: ONNX / SimCC モデルへ前処理画像を渡し、`RTMPOSE_BATCH_SIZE > 1` かつ動的バッチ対応 ONNX モデルの場合はバッチ推論します。
   - **ViTPose++ 選択時**: UDP アフィン変換・ImageNet 正規化を行い、キャッシュ済み ONNX Runtime（または PyTorch、CUDA 時は指定精度 `fp16`/`fp32`）で推論し、Flip Test（有効時）と UDP + DARK（FP32）によるサブピクセル座標復号を行います。
   - **ローカル実行時** はインメモリで作成した前処理画像を使って非同期ライターで 3 本の MP4 動画・CSV・NPZ・メタデータを保存し、**Colab 実行時** は Colab 側で推論と CSV/NPZ/メタデータ生成（`data_only`）のみ行ってローカル側で `render_videos_from_data` により 3 本の MP4 動画を並列書き出しします。

※ 同一セッション内の連続解析では常駐ワーカープロセス（`--persistent-worker`）でモデルを再利用して初期化待ちを短縮します。CPU 実行時・空き VRAM 上限到達時・CUDA OOM 発生時は自動的にバッチサイズを縮小（半減または `1` へフォールバック）して処理を継続し、GPU 実行時は空き VRAM に応じたプロセス上限（`set_per_process_memory_fraction`）を設定します。

---

## 8. 開発者向け情報（コマンドオプション・UI開発・自動テスト）

### コマンドラインオプション（`gui.py`）

```bash
python gui.py           # 標準起動（PyWebView + ビルド済み frontend/dist を使用）
python gui.py --dev     # Vite 開発サーバー (http://localhost:5173) に接続して起動
python gui.py --debug   # PyWebView デバッグモードを有効にして起動
```

※ 内部サブプロセス用に `--analysis-worker`（1ジョブ実行ワーカー）および `--persistent-worker`（連続実行・Colab サーバー用の常駐ワーカー）も用意されています。

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

# Colab ハイブリッド & CLI/SSH ランチャーテストのみ実行
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_colab*.py" -v

# 個別スイート（姿勢推定 / ViTPose / PyWebView / バンドル検証 等）
.\.venv\Scripts\python.exe -m unittest tests/test_pose_estimators.py
.\.venv\Scripts\python.exe -m unittest tests/test_api_bridge_vitpose.py
.\.venv\Scripts\python.exe -m unittest tests/test_pywebview_migration.py
.\.venv\Scripts\python.exe -m unittest tests/test_m3_bundle_and_build.py

# Node.js テスト（組み込み node:test ランナー）
node --test tests/test_event_deduplicator_adversarial.mjs tests/test_frontend_stress_m3.mjs tests/test_pywebview_telemetry_integration.mjs
```

**macOS（仮想環境有効化後）:**

```bash
python -m unittest discover -s tests
node --test tests/*.mjs
```

---

## 9. トラブルシューティング

- **「フロントエンドのビルドが必要です (`frontend/dist/index.html` が検出されませんでした)」と表示される**
  - `frontend/dist/` が削除されているか、古い状態で取得されています。Node.js 導入後に `cd frontend && npm install && npm run build` を実行してください。
- **Windows で起動しても画面が開かない・WebView 関連エラーが出る**
  - Windows 10 等で Microsoft Edge WebView2 ランタイムが未導入の可能性があります。[Microsoft Edge WebView2 公式](https://developer.microsoft.com/ja-jp/microsoft-edge/webview2/) からランタイムを導入してください。
- **NVIDIA GPU を積んでいるのに `実行デバイス: CPU` と表示される**
  - `requirements.txt` を後から実行した等で CPU版 `onnxruntime` が混入している可能性があります。[3.5 GPU環境とCPU環境についての補足・切り替え](#35-gpu環境とcpu環境についての補足切り替え) の再導入手順を実行してください。また NVIDIA ドライバーが古すぎないか（CUDA 13.0 対応か）もご確認ください。
- **Colab（SSH直結）で上位 GPU（`A100` / `L4` / `G4` / `H100`）の割り当てが失敗する**
  - 契約中の Colab プラン非対応・Compute Units 不足・一時的な空き枠不足・他 PC でのセッション残存（`[?]` 表示）などが原因です。設定モーダルの **「`T4` に切り替えて再試行」** を試すか、Google Colab（ブラウザ）の「ランタイム → セッションを管理」から不要セッションを解放してください。
- **Colab の Google Drive マウントが `MessageError: Error: credential propagation was unsuccessful` 等で失敗する**
  - Colab 側の一時的な Drive 認証障害やアカウント認証競合時に発生します。`SSH直結` モードではデフォルトで Drive キャッシュを OFF にしており、ON の場合でも失敗時は自動で `/content/.cache` のみへフォールバックして続行します。`手動URL（従来ノートブック）` モードをお使いの場合は、セル 1 の `USE_DRIVE_CACHE` のチェックを外して実行してください。
- **macOS で `rtmlib起動.command` をダブルクリックしても開けない**
  - `chmod +x rtmlib起動.command` を実行した後、Finder 上で **右クリック（Control＋クリック）→「開く」** を試してください。
- **ViTPose++ 初回実行時にモデル読み込みが進まない／エラーになる**
  - 未キャッシュのサイズ（`s` / `b` / `l` / `h`）を初めて使う場合のみ Hugging Face Hub への接続と初回 ONNX エクスポートが必要です。一度完了すれば 2 回目以降はキャッシュから高速読み込み・オフライン動作します。また既存の `.venv` で `transformers` や `onnx` が不足している場合は `python -m pip install "transformers>=4.49.0" "onnx>=1.16"` を実行してください。
