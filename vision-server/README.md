# vision-server

Raspberry Pi Camera Module の画像認識サーバです。Python の依存パッケージは
`vision-server/.venv` にインストールして利用します。

## マーカーコントローラ

`marker_controller.py` は赤・緑の2色マーカーを検出し、左右モーターのPWM値を
計算します。カメラ画像は、機体の進行方向が画面上になるよう上下反転してから解析・配信します。
ぬいぐるみの前後移動（画面中央から赤・緑の中点までの前後成分）を前進・後退速度に、
赤重心から緑重心への向きを旋回量にするため、マーカーを画面中央へ厳密に合わせなくても
前後移動とひねりを別々に操作できます。結果画像をMJPEGで配信するWebサーバも同時に起動します。

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

同時に `127.0.0.1:65432` でRasPike-ART向けTCPサーバーが起動します。クライアントが
`GET\n` を送ると、最新の左右PWM値を `<left>:<right>\n` 形式で返します。TCPサーバーは
ローカル接続だけを受け付けます。

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

`robot/direct_pwm_camera` は、TCPサーバーから受信した左右PWM値を直接モーターへ
設定する独立したRasPike-ARTアプリケーションです。通信値は `-100`～`100` に制限し、
通信失敗時にはモーターを停止します。

次のコマンドは、SDK workspaceへのシンボリックリンク作成、対象アプリのビルド、
生成された `asp` の起動を順に行います。

```console
./scripts/start-robot direct_pwm_camera
```

ビルドと起動を分ける場合は、次のように実行します。

```console
./scripts/build-robot direct_pwm_camera
./scripts/start-robot
```

引数なしの `start-robot` は既存の `asp`、つまり通常は最後に正常にビルドされたアプリを
起動します。直前のビルドが失敗した場合は、それより前の `asp` が残る可能性があるため、
通常はアプリ名を付けた起動を推奨します。
