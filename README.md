# raspike-spike-demo
Raspberry Pi 4 + LEGO SPIKE Prime demonstration programs

## ダッシュボード化の提案

電源投入後にアクセスポイントへ接続し、ブラウザだけでデモを操作できる環境の
構成案は [`docs/dashboard-proposal.md`](docs/dashboard-proposal.md) を参照してください。

## ダッシュボードを起動する

ダッシュボードには、自動検索ではなく `dashboard/programs.json` に登録した現在利用可能な
画像認識サーバーとマーカー追従プログラムだけが表示されます。初回だけ次を実行します。

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

インストールスクリプトは、manifest に登録した二つの unit に対する固定された操作だけを
sudoers へ登録し、ログ閲覧用グループを追加します。実行後は一度ログアウトして反映して
ください。任意の unit やコマンドは実行できず、Web サーバー自体も root では起動しません。
