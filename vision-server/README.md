# vision-server

現行のカメラ黒線ライントレースは `vision_server_picamera.py` と
[`robot/direct_pwm_camera/`](../robot/direct_pwm_camera/README.md) の組合せです。
旧 `robot/line_trace_camera/` は空白区切りの操舵値を期待し、現行PWM応答とは互換性がありません。
通常開発の編集・ビルド・実行は[学生向けガイド](../docs/student-development-guide.md)、
完成デモは[ルートREADME](../README.md)を参照してください。
ソースの正本はリポジトリ内です。SDKは別途 `~/RasPike-ART` に配置し、コピーやリンクは作りません。

## Python環境と起動・停止

Raspberry Pi Camera Module、Picamera2、OpenCV（cv2）、NumPy、Flaskが利用できる
`vision-server/.venv` を教員が用意します。`requirements.txt` は多数のOS関連パッケージを含むため、
PCでそのまま再現できる最小依存リストとは扱わず、実機の導入環境を確認してください。

SSHでは別ターミナルで以下を前景起動し、終了時は同じターミナルで `Ctrl+C` を押します。
Pythonを先に起動し、映像を確認してから名前指定ラッパーでCを起動します。

```bash
cd ~/raspike-spike-demo
./scripts/start-vision
```

`start-vision` は既存の同名Pythonをpkillしてから `.venv` で起動します。
停止はロボットの一時停止・終了を先に行い、その後Pythonを終了してください。
Webでは8082のダッシュボードからPythonを実行・停止します。WebとSSHの管理は混用しません。
8080は映像・パラメータ調整用で、ソース編集機能はありません。
マーカー用PythonとはカメラとTCPポートが共通のため同時起動しません。

## ライントレースのWeb調整

`vision_server_picamera.py` と `direct_pwm_camera` を組み合わせると、ブラウザの
`http://<Raspberry PiのIPアドレス>:8080/` から次の値を走行中に変更できます。

- 黒色・白色の基準値（二値化閾値には両者の中間値を使用）
- ライン進行方向ベクトルの旋回係数
- 直線時・カーブ時のベース速度
- 左右モーターへ加える旋回係数

設定は `vision-server/line_trace_settings.json` に保存され、次回起動時にも使われます。
操舵量が大きくなるほどベース速度はカーブ時速度へ近づきます。
ライン検出のconfidenceが0以下なら計算PWMは0になります。ただし画像更新自体が止まった場合の
鮮度失効とは別です。[停止処理の限界](../robot/direct_pwm_camera/README.md#停止処理と未確認事項)も確認してください。

## マーカーコントローラ

`marker_controller.py` は赤・緑の2色マーカーを検出し、左右モーターのPWM値を
計算します。カメラ画像は、機体の進行方向が画面上になるよう上下反転してから解析・配信します。
ぬいぐるみの前後移動（画面中央から赤・緑の中点までの前後成分）を前進・後退速度に、
赤重心から緑重心への向きを旋回量にするため、マーカーを画面中央へ厳密に合わせなくても
前後移動とひねりを別々に操作できます。結果画像をMJPEGで配信するWebサーバも同時に起動します。
右へひねると左PWMが正・右PWMが負、左へひねると左PWMが負・右PWMが正になります。
旋回量は中央の停止範囲の影響を受けないため、中央でも左右を逆方向へ回すその場旋回ができます。
中央の停止領域を出ると早めに操作量が立ち上がり、赤・緑のどちらかを見失った場合は
直前の指令を保持せず計算PWMを0にします。実モーターの停止時間は実機未確認です。

Web映像はプライバシー保護のため、検出した赤・緑マーカーの画素だけを表示し、背景や
マーカー以外の被写体は黒く隠します。色検出自体は上下反転後の元画像に対して行います。

Web画面の「モータ感度」スライダーでは、左右PWMを計算する際の出力倍率を0.5～6.0倍で
変更できます。初期値は1.5倍で、環境変数 `RASPIKE_SPEED_GAIN` でも指定できます。
PWMの上限は走行体側と同じ±100です。「中央の停止範囲」も0～30%で変更でき、初期値は
5%です（環境変数 `RASPIKE_DEADZONE` でも指定できます）。画面にはPython側の計算PWMと、
走行体が直前にモーターAPIへ設定したPWMを並べて表示します。後者もエンコーダーによる
回転検出値ではありませんが、指令がTCP通信で走行体まで届いたかを切り分けられます。
「黒線の判定値」ではカラーセンサーの反射光閾値を0～100で調整できます。初期値は8で、
薄茶色の床を黒と誤判定する場合は値を小さくします。小さすぎると黒線を見逃すため、実際の
床と黒線で停止を確認してください。初期値は環境変数 `RASPIKE_BLACK_THRESHOLD` でも指定できます。

Picamera2 の `RGB888` は `capture_array()` では OpenCV と同じ BGR
チャンネル順になるため、RGBからBGRへの追加変換をせず、そのまま色検出と
JPEG出力に使用しています。

起動スクリプトは実行時のカレントディレクトリに依存しません。たとえば、
リポジトリルートでは次のコマンドでバックグラウンド起動できます。

```console
./scripts/start-marker-controller
```

ブラウザで `http://<Raspberry PiのIPアドレス>:8081/` を開くと、検出結果を
重ねたカメラ画像を確認できます。`/status` では最新の検出有無、PWM値、角度などを
JSONで確認できます。

ログは `var/log/marker-controller.log`、PIDは
`var/run/marker-controller.pid` に保存されます。停止用スクリプトも実行時の
カレントディレクトリに依存しません。

```console
./scripts/stop-marker-controller
```


## TCPプロトコル（両サーバー共通）

ローカルの `127.0.0.1:65432` で受け付けます。

| 要求／応答 | 形式 |
| --- | --- |
| 現行Cの要求 | `GET <control_enabled> <emergency_stop> <applied_left> <applied_right> <r> <g> <b>\n` |
| 状態付きGETへの応答 | `<left>:<right>:<stop_mode>:<reflection_threshold>:<r_min>:<r_max>:<g_min>:<g_max>:<b_min>:<b_max>\n` |
| 単純な `GET\n` への互換応答 | `<left>:<right>\n` |

PWMは±100、RGB生値は0〜1023、stop_modeは0=無効、1=反射率、2=RGB範囲です。
現行Cは10項目応答と旧3項目の `left:right:reflection_threshold` 応答を受理しますが、
2項目の単純GET応答は受理しません。黒線ライントレースのPythonはmode=0を返すため、
本体カラーセンサーの黒線で停止させません。マーカー側では停止モードをWebで選択できます。
適用PWMの通知はモーターAPIへ直前に設定した値で、エンコーダーによる回転計測ではありません。

ブラウザ切断は自動停止条件ではありません。Python–C通信失敗の検出時の停止処理と、
無応答・画像更新停止は区別してください。今回の照合は静的確認のみで、実機停止動作は未確認です。
