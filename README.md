# raspike-spike-demo
Raspberry Pi 4 + LEGO SPIKE Prime demonstration programs

## ダッシュボード化の提案

電源投入後にアクセスポイントへ接続し、ブラウザだけでデモを操作できる環境の
構成案は [`docs/dashboard-proposal.md`](docs/dashboard-proposal.md) を参照してください。

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

Web サーバーは全インターフェースのポート 5000 で待ち受けます。PC を Raspberry Pi と同じ
ネットワーク（AP モードでは `raspike-ap`）へ接続し、画面に表示された URL、または
`http://192.168.60.1:5000/` を開いてください。終了はコンソールで `Ctrl+C` を押します。

インストールスクリプトは、manifest に登録した unit に対する固定された操作だけを
sudoers へ登録し、ログ閲覧用グループを追加します。実行後は一度ログアウトして反映して
ください。任意の unit やコマンドは実行できず、Web サーバー自体も root では起動しません。

### プログラムの組み合わせとポート

| 先に起動する Python プログラム | Web 画面 | 続けて起動するロボットプログラム |
|---|---|---|
| 画像認識サーバー | `http://<Raspberry Pi>:8080/` | カメラ・ライントレース |
| マーカー追従 | `http://<Raspberry Pi>:8081/` | カメラ直接PWM制御 |

Python プログラムのカードには、実際にダッシュボードへアクセスしたホスト名または IP を使った
「Web画面を開く」リンクが表示されます。ダッシュボードは 5000、各プログラムは 8080 と
8081 を使うため Web ポートは競合しません。ただし二つの Python プログラムは同じカメラを
使うため排他起動され、一方を実行するともう一方は停止します。

ダッシュボードと各 Python プログラムのポート番号は `dashboard/programs.json` で一元管理
しています。ポートを変更した場合は `scripts/install-dashboard-program-units` を再実行してから
ダッシュボードを起動してください。

ロボットプログラムの「実行」は対象アプリをビルドした後、RasPike-ART workspace で
`make start` を実行します。「停止」は systemd の control group 全体へ `SIGKILL` を送り、
`make` とその子プロセスを強制停止します。対応する Python サーバーが未起動の場合は、
systemd の依存関係によって先に自動起動します。また、ロボットプログラム同士も排他起動です。
