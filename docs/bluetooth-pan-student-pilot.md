# 学生向け：Bluetooth PAN 接続可否の事前調査（第1段階）

> **この文書の第1段階は、読む・確認するだけです。設定変更はしません。**
> 教員の確認が済むまでは、Bluetooth PAN の設定追加、ペアリング、ネットワーク切替を行わないでください。

## 目的と前提

車両型ロボット（Raspberry Pi 4 + SPIKE PRIME）の自由走行を維持しつつ、学生のWindows 11ノートPCで **学内Wi-Fiを維持したまま** Raspberry Piへ SSH / VS Code Remote-SSH で接続できるかを調べます。別経路として Bluetooth PAN を検討します。

- Raspberry Pi：Bluetoothネットワークを提供する **NAP（Network Access Point）** の役割
- WindowsノートPC：Bluetooth PANのクライアントの役割
- Bluetoothの普通のペアリングだけではSSH通信できません。NAPとIPネットワークの設定が必要です。
- 現在の実装では、機体APのSSIDは `iotNN`、AP側IPは `192.168.60.(100+NN)`、有線側は `192.168.50.(100+NN)` です。**Bluetooth側のIPは未決定**です。

参照：[既存ネットワーク設定](../scripts/setup)、[AP切替](../scripts/net-ap)、[Wi-Fi切替](../scripts/net-wifi)、[通常開発のSSH手順](student-development-guide.md)、[ロボットの停止に関する注意](../README.md)。

## 第1段階：読み取り専用の調査（学生が実施してよい範囲）

### 作業前

1. 教員に利用する機体番号を確認し、別の学生・デモが使っていない機体を選びます。
2. ロボットの車輪が不意に動かないよう、安全に置きます。**この調査でモーターやカメラ用プログラムを起動しません。**
3. 現状のSSH接続方法（機体APまたは有線）を教員・担当者に確認します。**接続確保のために学内ネットワークの設定を変更しません。**
4. Pi側の既存の未保存ソース・変更があれば、触れずに教員へ報告してください。

### Raspberry Pi側（現在のSSHセッションで実行）

以下は読み取り専用です。コマンドが見つからない場合はそのまま報告し、インストールしません。

```bash
cat /etc/os-release
uname -m
nmcli --version
bluetoothctl --version
systemctl is-active bluetooth
bluetoothctl show
nmcli -f DEVICE,TYPE,STATE device status
nmcli -f NAME,TYPE,DEVICE connection show --active
```

確認項目：OS名・版、64bit/32bit、NetworkManager/BlueZの有無、Bluetoothの `Powered: yes/no`、現在の接続方式。**`bluetoothctl show` などに表示されるBluetoothアドレス（MAC）は報告前に伏せてください。**

**禁止：** `sudo` によるサービス・設定変更、`nmcli connection add/modify/up/down`、`bluetoothctl pair/trust/connect`、`scripts/setup`、`scripts/net-ap`、`scripts/net-wifi`、再起動、パッケージの追加・更新、ロボットのプログラム起動、既存Git作業内容の破棄。

### ノートPC側（Windows 11の場合）

1. Windows 11のバージョンと、Bluetoothが「設定 → Bluetoothとデバイス」で利用可能であることを確認します。
2. PowerShellを通常権限で開き、次の読み取り専用コマンドを実行します。

```powershell
Get-PnpDevice -Class Bluetooth |
    Select-Object FriendlyName, Status
Get-NetAdapter |
    Select-Object Name, InterfaceDescription, Status
```

3. 学内Wi-Fiを利用中であれば、そのままにします。**この段階ではBluetoothペアリングもPAN接続も試しません。**

Windows 11でPANを使う場合の公式操作は「設定 → Bluetoothとデバイス → デバイス → 対象機器 → PANへ参加」です。ただし、**Pi側でNAPが有効でなければ参加できません**。第2段階までは操作不要です。

### 教員への報告（個人情報・パスワードは不要）

```text
機体番号：
ノートPCのOS（Windows 11など）：
Pi OS名・版、アーキテクチャ：
NetworkManagerの版：
Bluetoothツールの版：
bluetoothサービスの状態：
bluetoothctl showの Powered 状態：
Piの現在の接続方式（機体AP／有線など）：
WindowsのBluetooth機器の状態：
実行できなかったコマンド・エラー：
既存SSHの接続方法が残っているか：
```

機体のMACアドレス、学内SSIDやパスワード、SSH秘密鍵、認証トークン、個人のアカウント情報は報告に含めないでください。

## 第2段階：Bluetooth PAN実接続（**未承認・未実施**）

以下は教員が第1段階の報告を確認してから、**別途承認し手順を確定する試験計画**です。現時点では実行しません。

1. 対象機体1台、Windows 11ノートPC1台に限定する。Piの現行AP・有線・SSHの復旧手段を確保する。
2. Raspberry Pi上に専用のBluetooth NAP接続を設計する。Wi-Fi APの既存設定や学内Wi-Fi接続を変更しない。必要なパッケージ／BlueZ／NetworkManagerの互換性を先に確認する。
3. 学内LANへのブリッジ・インターネット共有を行わず、**Bluetooth経路をPi宛てのローカル通信用に限定する**。Windows側でデフォルトゲートウェイ・DNS・経路が学内Wi-Fiから変わらないか調べる。既存の `192.168.50.0/24` と `192.168.60.0/24` との重複を避ける。
4. WindowsとPiをペアリングしてPAN接続する。接続後のIP、疎通、SSH、VS Code Remote-SSHを確認する。初回VS Code Server導入の通信条件も確認する。
5. 学内Wi-Fiを維持してWebClass/GitHub等にアクセスできるか確認する。Wi-Fi側の資格情報は調査・記録しない。
6. まずモーターを動かさず、SSH操作の応答と再接続を確認する。カメラ映像や走行・10組同時の安定性は別途、教員立会いで段階的に評価する。
7. 終了時にはPAN接続を切断し、既存AP・有線・SSHが引き続き利用できることを確認する。設定を残す・削除する判断は教員が行う。

**注意：** PC側の通信断、VS Codeの切断、ブラウザ画面の停止はロボット停止の保証ではありません。機体の物理的な停止方法は教員が確認してください。

## 参考

- [Microsoft：WindowsでBluetoothネットワークに接続](https://support.microsoft.com/ja-jp/windows/hardware/bluetooth/connect-to-a-bluetooth-network-in-windows)
- [NetworkManager：nmcli examples / Bluetooth connection profiles](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nmcli-examples.html)

この文書は学生による初期調査用のドラフトです。**Bluetooth PANが実機で使えることを示す検証結果ではありません。**
