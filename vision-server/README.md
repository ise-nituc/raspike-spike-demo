# vision-server

Raspberry Pi Camera Module の画像認識サーバです。Python の依存パッケージは
`vision-server/.venv` にインストールして利用します。

## マーカーコントローラ

`marker_controller.py` は赤・緑の2色マーカーを検出し、左右モーターのPWM値を
計算します。結果画像をMJPEGで配信するWebサーバも同時に起動します。

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

## RasPikeアプリケーションとの関係

RasPike-ART本体はこのリポジトリには置きません。別途
`~/RasPike-ART` に用意してください。このリポジトリの `robot/appdir` は、SDK側の
`~/RasPike-ART/sdk/workspace/appdir` を指すシンボリックリンクとして作成する前提です。

```console
ln -s "$HOME/RasPike-ART/sdk/workspace/appdir" robot/appdir
./scripts/build-robot
```

シンボリックリンク先にある機体固有設定やビルド生成物は、このリポジトリには
コミットしないでください。
