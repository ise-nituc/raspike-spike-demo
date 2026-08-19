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
- クライアント要求: `GET <control_enabled> <emergency_stop> <applied_left> <applied_right> <r> <g> <b>\n`
- サーバー応答: `<left>:<right>:<stop_mode>:<reflection_threshold>:<r_min>:<r_max>:<g_min>:<g_max>:<b_min>:<b_max>\n`
- PWM値の範囲: `-100`～`100`
- RGB値の範囲: `0`～`1023`（カラーセンサーの10 bit生値）。`stop_mode` は0=無効、1=反射率、2=RGB範囲です。

受信値は安全のためRasPike-ART側でも `-100`～`100` に制限します。通信失敗時と
一時停止時には左右のモーターを停止します。マーカー追従Web画面では、カラーセンサーによる
緊急停止を無効・反射率・RGB範囲から選べます。ライントレースではこの緊急停止を無効にします。
フォースセンサーと緊急停止の状態はPWM要求と一緒にサーバーへ通知され、Web画面に表示されます。
直前の制御周期でモーターAPIへ設定した左右PWMも通知されるため、Web画面でPython側の
計算PWMが走行体まで届いたか確認できます（エンコーダーによる実回転の検出ではありません）。
この拡張値を表示するには、変更後の `direct_pwm_camera` を再ビルドして走行体を再起動して
ください。旧バイナリとの通信自体は継続できますが、「ロボット適用PWM」は通信待ち表示になります。
`marker_controller.py` が返す値も現在は `-100`～`100` です。

## 操作

フォースセンサーを押すと制御を開始し、もう一度押すと一時停止します。モーターは
左がポートB、右がポートA、カラーセンサーがポートE、フォースセンサーがポートDです。
