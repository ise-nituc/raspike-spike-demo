# スクリプトの案内・機体設定

通常開発の正式手順は[学生向けガイド](../docs/student-development-guide.md)、
完成デモのWeb操作は[ルートREADME](../README.md)を参照してください。
以下はリポジトリルートでの指定です。設定・インストール・ネットワーク切替は教員向けで、検証のためだけに実行しません。

| 入口 | 動作・注意 |
| --- | --- |
| `./scripts/build-robot direct_pwm_camera` | `robot/direct_pwm_camera/` を参照してSDKでビルド、またはキャッシュ復元。引数なしはSDKの `appdir` 用の互換経路 |
| `./scripts/start-robot direct_pwm_camera` | 共通ロックを保持してビルド／キャッシュ復元後に `make start`。ビルド失敗時は起動しない。通常はこれだけでよい |
| `./scripts/start-robot`（互換） | 名前なしは既存 `asp` をそのまま実行。古い／別アプリの恐れがあり通常手順にしない |
| `./scripts/start-vision` | 既存同名Pythonを停止後、`.venv` で `vision_server_picamera.py` を前景起動。終了は同じ端末でCtrl+C。stop-visionはない |
| `./scripts/start-marker-controller` / `./scripts/stop-marker-controller` | マーカーPythonをバックグラウンド起動／PIDで停止。ログは `var/log/marker-controller.log`、PIDは `var/run/marker-controller.pid` |
| `./scripts/start-dashboard` | ダッシュボードを前景起動。Ctrl+Cはダッシュボードの終了でありデモの停止ではない |
| `./scripts/install-dashboard-program-units [--enable-dashboard]` | unitと固定sudo許可を導入。オプション付きのみダッシュボードをenable --now。デモunitは自動起動しない |
| `./scripts/net-ap` / `./scripts/net-wifi` | wlan0のAP／Wi-Fi接続を切替。SSH切断の可能性があるため教員が操作 |
| `./scripts/start-demo` / `./scripts/stop-demo`（互換） | 前者はvisionと名前なし既存aspを起動。後者はvision PIDのみ停止しロボットは停止しない。現行カメラデモの標準入口にはしない |

ロボットの停止は、SSHならフォース操作で一時停止後、起動端末のCtrl+C、Webならロボットの「停止」を使い、
その後Pythonを停止します。実機の停止を確認してください。[停止保証の限界](../README.md#実行管理と安全上の確認)も参照してください。

SDK workspaceは `~/RasPike-ART/sdk/workspace`、ソースの正本はリポジトリの `robot/` と `vision-server/` です。
ビルドはソースへの相対パスを `make img=` に渡し、コピー・リンク作成は不要です。
`var/cache/asp/<key>/` は対象アプリ配下のファイルとSDK内容等のハッシュによるキャッシュです。
hitなら共通のworkspace/aspを復元、missならビルドします。コンパイラ版等を網羅した再現性や
成果物の同一性を保証するものではありません。`ready/running` も実機停止・起動成功の証明ではありません。

Webのsystemd ConflictsとCLIのflockは管理範囲が違います。混用せず、切替前に元の経路で終了し、
待機中の起動も残さないでください。直接makeはラッパーを迂回するため通常手順にせず、教員の診断に限ります。

## クローン機体の設定（教員向け）

After booting a cloned IoT01 microSD card, update the repository and assign the
new two-digit robot ID:

```bash
cd ~/raspike-spike-demo
git status
# 未保存・他の学生の変更がないことを確認してから更新
git switch main
git pull --ff-only
cd scripts
./setup 02
sudo reboot
```

For normal updates from the public repository, an HTTPS `origin` is recommended.
It does not need to be reset on every update. If `git pull` fails with
`git@github.com: Permission denied (publickey)`, inspect and change the remote:

```bash
git remote -v
git remote set-url origin https://github.com/ise-nituc/raspike-spike-demo.git
```

`setup` accepts IDs from `01` through `99`. It previews all derived addresses
and asks for confirmation. It saves NetworkManager settings without cycling
connections, so the current SSH session should remain available until reboot.

The script manages only `raspike-eth` and the existing `raspike-ap`. It neither
changes nor deletes school Wi-Fi connections such as `netplan-wlan0-isepr`.
When `/etc/raspike-id` records a different ID, clone-specific machine and SSH
host identities are regenerated once. If no prior ID is recorded, identities
are left unchanged; inspect the machine before deciding whether regeneration is
needed.

## Verification after reboot

For ID `02`, the expected checks are:

```bash
hostnamectl hostname
cat /etc/raspike-id
nmcli -f connection.id,connection.interface-name,connection.autoconnect,connection.autoconnect-priority,ipv4.method,ipv4.addresses connection show raspike-eth
nmcli -f connection.id,connection.interface-name,connection.autoconnect,connection.autoconnect-priority,802-11-wireless.ssid,802-11-wireless.mode,ipv4.method,ipv4.addresses connection show raspike-ap
ip -4 address show dev eth0
ip -4 address show dev wlan0
```

Expected values are hostname `IoT02`, Ethernet `192.168.50.102/24`, AP SSID
`iot02`, and AP address `192.168.60.102/24`. The script intentionally does not
delete legacy `netplan-eth0`, `Wired connection 1`, or anything under
`/var/lib/NetworkManager`; `raspike-eth` has priority 100 and is selected after
reboot without risking unrelated or secret connection data.

As in the previous `/home/iot/setup`, completion output also includes the
port-8082 dashboard addresses, current runtime interface information, host-key
cleanup commands after clone identity regeneration, and an optional reboot
prompt.
