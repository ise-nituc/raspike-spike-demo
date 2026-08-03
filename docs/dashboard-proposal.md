# Raspike-ART デモ環境のダッシュボード化案

## 1. 目標と利用手順

教員がターミナルを操作せず、次の手順だけでデモを開始できる状態を目標とします。

1. Raspberry Pi と SPIKE Prime の電源を入れる。
2. PC またはタブレットを、Raspberry Pi の Wi-Fi（例: `Raspike-Demo-XXXX`）へ接続する。
3. ブラウザで `http://raspike.local/` を開く。名前解決できない端末では
   `http://192.168.60.1/` を開く。
4. ダッシュボードでプログラムを選び、「実行」または「停止」を押す。

既存の `scripts/net-ap`、`scripts/start-*` を手動実行する方式は、開発・復旧用として
残します。

## 2. 推奨構成

```text
PC / tablet
    |
    | Wi-Fi (192.168.60.0/24)
    v
NetworkManager hotspot ── Raspberry Pi
                              |
                              +─ nginx (:80)
                              |    └─ dashboard API (127.0.0.1:8000)
                              |
                              +─ systemd
                                   ├─ Python demo units
                                   └─ Raspike-ART demo units
```

責務を次のように分離します。

- **NetworkManager**: AP の自動起動、固定 IP、DHCP、必要なら外部回線との共有。
- **nginx**: ポート 80 で画面を配信し、API をローカルの Web アプリへ転送。
- **Web アプリ**: 一覧と状態を返し、許可された操作だけを systemd に依頼。
- **systemd**: プロセスの開始・停止、ログ、終了処理、二重起動防止を担当。

Web アプリから任意のシェルコマンドを実行する設計や、PID ファイルだけでプロセスを
管理する設計は避けます。実行可能なプログラムを設定ファイルで明示し、systemd の
ユニット名へ対応付ける方式が安全で、停止や障害調査も容易です。

## 3. 起動設定

### 3.1 アクセスポイント

現在の `scripts/net-ap` が使用する NetworkManager 接続 `raspike-ap` を自動接続にします。
初回のイメージ作成時に、概ね次の設定を行います（接続を新規作成する場合は先に
`nmcli connection add type wifi ifname wlan0 con-name raspike-ap autoconnect yes ssid ...`
などで作成します）。

```console
sudo nmcli connection modify raspike-ap \
  connection.autoconnect yes \
  connection.autoconnect-priority 100 \
  802-11-wireless.mode ap \
  802-11-wireless.band bg \
  ipv4.method shared \
  ipv4.addresses 192.168.60.1/24 \
  ipv6.method disabled \
  wifi-sec.key-mgmt wpa-psk \
  wifi-sec.psk '<十分に長いパスフレーズ>'
sudo nmcli connection modify netplan-wlan0-isepr connection.autoconnect no
sudo nmcli connection up raspike-ap
```

`band bg`（2.4 GHz）は端末互換性を優先した案です。会場の混雑状況に合わせてチャネルを
固定する場合は、事前に現地で確認します。SSID は複数台を識別できるよう、筐体ラベルと
末尾4桁を一致させます。パスフレーズも筐体に表示します。

授業用 AP を常時優先し、校内 Wi-Fi への切り替えは保守担当者だけが
`scripts/net-wifi` で行う運用にします。AP 起動失敗時にも有線 SSH で復旧できる構成を
残してください。

### 3.2 Web アプリの自動起動

ダッシュボードは専用ユーザー `raspike-dashboard` で動かし、systemd unit を
`multi-user.target` から有効化します。

```ini
[Unit]
Description=Raspike demo dashboard
After=network.target

[Service]
Type=simple
User=raspike-dashboard
Group=raspike-dashboard
WorkingDirectory=/opt/raspike-spike-demo/dashboard
ExecStart=/opt/raspike-spike-demo/dashboard/.venv/bin/gunicorn \
          --bind 127.0.0.1:8000 'app:create_app()'
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

開発サーバーを直接公開せず、nginx から `127.0.0.1:8000` へ中継します。最初の版では
HTTP でも閉じた AP 内に限定できますが、パスワードを扱う場合や校内 LAN に接続する場合は
HTTPS を導入します。

## 4. Web アプリ（ダッシュボード）

### 4.1 画面

一画面で次を表示します。

- 上部: Raspberry Pi 名、AP の SSID/IP、CPU 温度、空き容量、最終更新時刻。
- **Python プログラム**: 名前、説明、状態（停止中/起動中/失敗）、実行、停止、ログ表示。
- **Raspike-ART プログラム**: 名前、説明、ビルド状態、実行、停止、ログ表示。
- 下部: 「Raspberry Pi を再起動」ボタン。

誤操作を減らすため、実行中は同じ行の「実行」を無効化し、停止と再起動には確認画面を
出します。API の処理結果だけで成功表示せず、systemd から取得した実状態を数秒ごとに
更新します。停止に失敗した場合は「停止中」のままにせず、エラーとログへの導線を
表示します。

### 4.2 プログラムの登録

リポジトリ全体を走査して任意ファイルを実行せず、例えば次の manifest だけを一覧に
載せます。

```yaml
programs:
  - id: marker-controller
    category: python
    label: マーカー追従
    description: カメラで赤・緑のマーカーを検出します
    unit: raspike-marker-controller.service
  - id: direct-pwm-camera
    category: raspike-art
    label: カメラ直接PWM制御
    description: 検出結果を左右モーターへ反映します
    unit: raspike-direct-pwm-camera.service
```

`id` と `unit` は起動時に許可リストとして検証します。ラベルと説明だけを画面に出し、
コマンド、ファイルパス、ユーザー入力をシェル文字列として連結しません。

### 4.3 API 案

| Method | Path | 動作 |
|---|---|---|
| `GET` | `/api/programs` | 登録プログラムと systemd の状態を返す |
| `POST` | `/api/programs/{id}/start` | 対応する unit を開始する |
| `POST` | `/api/programs/{id}/stop` | 対応する unit を停止する |
| `GET` | `/api/programs/{id}/logs?lines=100` | 末尾のログを返す |
| `GET` | `/api/system` | ホスト名、温度、容量、稼働時間を返す |
| `POST` | `/api/system/reboot` | 確認トークン付きで再起動する |

状態変更 API は `POST` に限定し、CSRF 対策を入れます。初期版でも AP パスフレーズに加え、
操作用 PIN（授業ごと、または機体ごと）を設けるのが望ましいです。連打を防ぐレート制限と、
誰がいつ何を実行・停止・再起動したかの監査ログも残します。

### 4.4 systemd への権限委譲

Web アプリ自体を root で実行しないでください。次のいずれかで、許可した unit の
`start`、`stop`、`show` と再起動だけを委譲します。

1. **推奨**: 小さな root 権限の管理サービスを D-Bus/Unix socket 越しに呼び、unit 名を
   再度許可リストで検証する。
2. **小規模な試作**: `sudoers` で引数を固定したラッパースクリプトだけを許可する。

`sudo systemctl *`、任意引数を受け取るラッパー、Web アプリへのパスワードなし root 権限は
禁止します。再起動 API も同じ管理サービスを経由させます。

## 5. デモプロセスの扱い

Python プログラムは foreground で動く systemd unit に変換します。既存の
`start-marker-controller` のように子プロセスを background 化する処理は unit 内では
使わず、`ExecStart` に Python を直接指定します。これにより systemd が正しい PID を追跡し、
標準出力・標準エラーを journal に保存できます。

Raspike-ART は次の二段階に分けます。

- **イメージ準備時**: 全アプリをビルドし、実行物をアプリごとの固定ディレクトリへ保存。
- **授業中**: 選択済みの実行物を起動するだけにし、ビルドはしない。

現状の `start-robot <name>` は起動直前にビルドするため、待ち時間や失敗が授業に影響します。
ダッシュボードではビルド済み成果物の存在とハッシュを起動前に検査し、存在しなければ
「準備が必要」と表示します。また、ロボットを占有する unit 同士に競合制御を入れ、同時に
二つの Raspike-ART プログラムを起動しないようにします。

停止時にはまず通常終了（`SIGTERM`）を送り、一定時間後に強制終了します。どの停止方法で
SPIKE Prime のモーターが確実に停止するかを実機で検証し、通信断・Web アプリ停止・Raspberry
Pi 再起動時にもモーターを停止するフェイルセーフを各プログラムに持たせます。

## 6. 障害時の使いやすさ

- 電源投入中、AP 準備完了、デモ実行中、異常を LED の色や点滅で区別する。
- `raspike.local` が使えない場合に備え、固定 IP を筐体へ印刷する。
- ダッシュボードに「接続診断」を置き、カメラ、SPIKE Prime、必要ファイルを個別表示する。
- ログは journal に集約し、画面では末尾だけを個人情報を除いて表示する。
- SD カード破損に備え、構築手順をスクリプト化し、復旧用イメージも保管する。
- ハード電源断を避けるため、画面の再起動に加えて安全なシャットダウン手段も用意する。

## 7. 導入順序と受け入れ条件

### Phase 1: 自動 AP と読み取り専用画面

- 起動後 60 秒以内に SSID が見える。
- 固定 IP と `raspike.local` の少なくとも一方で画面を開ける。
- 登録プログラムと実際の状態が表示される。

### Phase 2: Python プログラム操作

- 実行、停止、二重起動防止、ログ表示が動く。
- Web アプリを再起動しても、デモの実状態を正しく再取得する。
- 不正なプログラム ID や unit 名を指定しても実行できない。

### Phase 3: Raspike-ART と再起動

- ビルド済みの各アプリを排他的に実行・停止できる。
- 画面からの再起動後、AP とダッシュボードが自動復帰する。
- 通信断、プロセス異常、停止、OS 再起動の全ケースでモーターが安全に停止する。

### Phase 4: 授業での試行

- 手順書を見た初見の教員が、ターミナルなしで接続からデモ終了まで行える。
- 複数台を同室で起動しても SSID と機体を取り違えない。
- 連続した授業時間を想定した長時間試験後も、再操作とログ取得ができる。

まず Phase 1 と Python プログラム一つで縦方向の試作を行い、教員による操作試験をしてから
対象プログラムを増やすと、UI と権限設計を小さい範囲で検証できます。
