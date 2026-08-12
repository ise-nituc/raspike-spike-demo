# direct_pwm_camera

TCPサーバーから左右モーターのPWM値を直接取得して走行するRasPike-ART用の
アプリケーションです。`line_trace_camera` とは独立しています。

リポジトリルートから次のコマンドを実行すると、ビルドスクリプトがこのディレクトリを
RasPike-ARTの `sdk/workspace/direct_pwm_camera` へコピーし、workspace 内で
`make app=direct_pwm_camera` を実行します。

```console
./scripts/build-robot direct_pwm_camera
```

ビルド済みの `asp` を起動するだけなら、アプリ名を付けずに実行します。

```console
./scripts/start-robot
```

起動対象を明示して、ビルド後すぐに起動することもできます。

```console
./scripts/start-robot direct_pwm_camera
```

RasPike-ARTの `make start` はworkspaceにある現在の `asp` を起動するため、アプリ名を
省略した場合は最後に正常にビルドされて `asp` を更新したアプリが実行されます。
ビルドに失敗した場合は以前の `asp` が残る可能性があるので、通常はアプリ名を指定する
起動方法を推奨します。

## TCPプロトコル

- 接続先: `127.0.0.1:65432`
- クライアント要求: `GET <control_enabled> <black_stop>\n`
- サーバー応答: `<left>:<right>\n`
- 値の範囲: `-100`～`100`

受信値は安全のためRasPike-ART側でも `-100`～`100` に制限します。通信失敗時と
一時停止時には左右のモーターを停止します。また、ポートEのカラーセンサーの反射光が
15未満（白30・黒0の中間値）の場合は、サーバーから受け取った値にかかわらず左右のモーターを停止します。
黒が解除されると、次の周期からサーバーの制御値に従って走行を再開します。
フォースセンサーによる制御ON/OFFと黒線停止の状態は、PWM要求と一緒にサーバーへ通知され、
マーカー追従Web画面に表示されます。
`marker_controller.py` が返す値は現在
`-50`～`50` ですが、同じプロトコルで `-100`～`100` を返す別サーバーも利用できます。

## 操作

フォースセンサーを押すと制御を開始し、もう一度押すと一時停止します。モーターは
左がポートB、右がポートA、カラーセンサーがポートE、フォースセンサーがポートDです。
