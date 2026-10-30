# raspike-spike-demo
Raspberry Pi 4 + LEGO SPIKE Prime demonstration programs

## 開発と完成デモ

カメラ黒線ライントレースの現行構成は、Pythonの
`vision-server/vision_server_picamera.py` とCの `robot/direct_pwm_camera/` です。
旧 `robot/line_trace_camera/` は操舵値の通信形式が異なり、現行Pythonとは組み合わせられません。

通常開発はSSH／VS Code Remote SSHで行い、[学生向け開発・保存・提出手順](docs/student-development-guide.md)
を正式手順とします。ソースの正本はリポジトリの `robot/` と `vision-server/`、
SDK workspaceはビルド・実行用です。完成デモには以下のWebダッシュボードを推奨します。
現行Webにはソース編集機能はありません。
[初期設計案](docs/dashboard-proposal.md)や[将来のWeb編集検討](docs/architecture/web-editor-feasibility.md)
は、現在利用可能な機能の説明ではありません。

## ダッシュボードを起動する

ダッシュボードには、自動検索ではなく `dashboard/programs.json` に登録した現在利用可能な
Python サーバーと Raspike-ART ロボットプログラムだけが表示されます。初回だけ次を実行します。

```console
python3 -m venv dashboard/.venv
dashboard/.venv/bin/pip install -r dashboard/requirements.txt
scripts/install-dashboard-program-units
```

unit のインストールは自動起動を有効にしません。ダッシュボードはコンソールから起動します。

```console
scripts/start-dashboard
```

Web サーバーは全インターフェースのポート 8082 で待ち受けます。PC を Raspberry Pi と同じ
ネットワーク（AP モードのSSIDは `iotNN`）へ接続し、画面に表示された URL、または
`http://<Raspberry PiのAP側IP>:8082/` を開いてください。AP 側 IP は Robot ID `NN` に対して
`192.168.60.(100+NN)` です（例: `IoT04` は `http://192.168.60.104:8082/`）。終了はコンソールで `Ctrl+C` を押します。

ダッシュボードを Raspberry Pi の起動時に自動起動したい場合は、初期設定の最後のコマンドに
`--enable-dashboard` を付けます。この指定がない場合は、従来どおり自動起動の状態を変更しません。

```console
scripts/install-dashboard-program-units --enable-dashboard
```

このオプションは `raspike-dashboard.service` を `systemctl enable --now` し、その場での起動と
次回以降のOS起動時の自動起動を設定します。プログラム用unitは自動起動されません。

インストールスクリプトは、manifest に登録した unit に対する固定された操作だけを
sudoers へ登録し、ログ閲覧用グループを追加します。実行後は一度ログアウトして反映して
ください。任意の unit やコマンドは実行できず、Web サーバー自体も root では起動しません。

### プログラムの組み合わせとポート

| 先に起動する Python プログラム | Web 画面 | 続けて起動するロボットプログラム |
|---|---|---|
| 黒線ライントレース（カメラ） | `http://<Raspberry Pi>:8080/` | カメラ用ロボット制御（direct_pwm_camera） |
| マーカー追従 | `http://<Raspberry Pi>:8081/` | カメラ用ロボット制御（direct_pwm_camera） |

Python プログラムのカードには、実際にダッシュボードへアクセスしたホスト名または IP を使った
「Web画面を開く」リンクが表示されます。ダッシュボードは 8082、各プログラムは 8080 と
8081 を使うため Web ポートは競合しません。ただし二つの Python プログラムは同じカメラを
使うため排他起動され、一方を実行するともう一方は停止します。

ダッシュボードと各 Python プログラムのポート番号は `dashboard/programs.json` で一元管理
しています。ポートを変更した場合は `scripts/install-dashboard-program-units` を再実行してから
ダッシュボードを起動してください。

ロボットプログラムの「実行」は対象アプリをビルドした後、RasPike-ART workspace で
`make start` を実行します。「停止」は systemd の control group 全体へ `SIGKILL` を送り、
`make` とその子プロセスを強制停止します。`direct_pwm_camera` はPythonサーバーを自動起動しません。
先に適切なPythonを起動してください。また、ロボットプログラム同士も排他起動です。
`make start` が内部で実行する固定の RasPike-ART 起動コマンドにはパスワードなしの `sudo` が
必要なため、既に unit をインストール済みの場合も `scripts/install-dashboard-program-units` を
再実行して sudoers 設定を更新してください。

### カメラ黒線ライントレースのデモ手順

教員によるSDK・Python環境・unit・機体の準備後に行います。

1. Raspberry PiとSPIKE Primeを起動し、機体番号を確認します。PCを機体APのSSID `iotNN` に接続します（パスフレーズは教員に確認）。有線LANや校内Wi-Fiの場合は教員が確認した到達可能なIPを使います。
2. `http://<PiのIP>:8082/` を開きます。Robot ID `04` のAPなら `http://192.168.60.104:8082/` です。
3. Pythonの「黒線ライントレース（カメラ）」で「実行」を押し、ログと「Web画面を開く」（8080）で映像・黒線検出を確認します。
4. ロボットの「カメラ用ロボット制御」で「実行」を押します。「旧カメラ・ライントレース」は選びません。この操作は `start-robot direct_pwm_camera` により対象のビルド（キャッシュhitなら復元）後に起動します。失敗時はログを確認し、古い `asp` を手動起動しないでください。
5. 初期状態は一時停止です。周囲と車輪を確認し、ポートDのフォースセンサーを押して離すと走行開始、次に押して離すと一時停止、再度同じ操作で再開します。8080では映像と走行設定、ロボットからの通知を確認できます。
6. 終了時はフォースセンサーで一時停止して機体の停止を目視確認し、ダッシュボードで「カメラ用ロボット制御」の「停止」、続いてPythonの「停止」を押します。両方のログ・状態と実機を確認します。ブラウザを閉じるだけでは終了しません。ダッシュボード自体の終了もデモ停止の代わりにはなりません。

`raspike-ap` はNetworkManagerの接続プロファイル名で、SSIDではありません。
`setup` の設定値はホスト名 `IoTNN`、APのSSID `iotNN`、AP IP `192.168.60.(100+NN)/24`、
有線IP `192.168.50.(100+NN)/24` です。校内Wi-Fiはそのネットワークの割当IPを確認します。
名前解決できない場合はIPを使い、実際の設定は[設定確認手順](scripts/README.md)で照合してください。

### 実行管理と安全上の確認

Webはsystemdで管理し、unit間のConflictsでロボット同士・Python同士を排他にします。
SSHの手動起動はこの管理外です。ラッパーの共通flockだけではWebとSSHの管理を統一できず、
ロック待ちの起動が後から進むこともあります。両経路を混用せず、切替前に元の経路で全プログラムを終了し、
待機中の起動要求も残っていないことを確認してください。

ブラウザの切断・タブを閉じる操作・PCのスリープでは自動停止しません。映像停止を機体停止と判断しないでください。
Python–Cの通信失敗をCが検出した場合はモーター停止処理がありますが、Cの受信期限とPythonの画像鮮度による
指令失効は確認できません。無応答・画像処理停止で一定時間内に止まる保証はありません。
機体操作と停止処理の詳細は[C側の説明](robot/direct_pwm_camera/README.md)を参照してください。

Webの `ready` / `running` は状態ファイル・プロセスの表示であり、機体の停止、起動成功、
実行物とソースの一致を証明しません。Web停止はプロセス群へのSIGKILLで、実モーター停止の保証とは別です。
今回の確認は静的照合のみです。フォース操作、Ctrl+C、SIGKILL、通信異常時の停止時間・距離は実機未確認です。
停止しない場合は再起動要求を重ねず、教員が事前に実機で確認した物理停止手段を使用してください。

### 再起動と電源オフ

画面下部の「再起動」と「電源オフ」から、確認後に Raspberry Pi を操作できます。インストール
スクリプトは `dashboard/programs.json` の `system_actions` に明示した `systemctl reboot` と
`systemctl poweroff` だけをパスワードなしで許可します。任意の sudo コマンドは実行できません。
