python3 -m pip install -r requirements.txt　を入力
次の設定をいじる

INPUT_VIDEO = Path("input.mp4") ←←← カッコ内を解析したい動画ファイルの名前に
OUTPUT_VIDEO = Path("output_pose.mp4") ←←← 骨格動画のファイル名
OUTPUT_JSON = Path("output_pose.json") ←←← 座標JSONのファイル名
以下をターミナルで実行

python3 main.py

JSON はフレームごとに `persons` を持ち、各人物の17部位（鼻、左目、右目、左耳、右耳、左肩、右肩、左肘、右肘、左手首、右手首、左股関節、右股関節、左膝、右膝、左足首、右足首）を記録します。各部位には `x`、`y`、`score` が入ります。