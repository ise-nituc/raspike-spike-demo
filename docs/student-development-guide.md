# 学生向け：ラズパイでの開発・保存・提出の手順

対象は `raspike-spike-demo` の `direct_pwm_camera` を編集する学生です。Webダッシュボードはデモ用とし、普段の開発ではSSH／VS Code Remote SSHから名前指定ラッパーを実行します。GitHubへの書き込み権限は不要です。

## 1. 編集する場所

以下の配置を前提とします。異なる場合は教員に確認して読み替えてください。

| 場所 | 役割 |
| --- | --- |
| `~/raspike-spike-demo/robot/direct_pwm_camera/` | 編集するCソースの正本 |
| `~/raspike-spike-demo/vision-server/` | カメラ画像からモーター指令を計算するPythonプログラム |
| `~/RasPike-ART/sdk/workspace/` | SDKでビルド・実行する場所 |

`~` はログイン中のユーザーのホームディレクトリです。ソースのディレクトリ名は `robot`（単数形）です。SDKのworkspaceに同名フォルダがあっても、そちらは編集しません。

SDK、Pythonの仮想環境、機体の接続は教員が設定済みとします。Webから起動したロボットと画像認識プログラムは作業前に停止してください。ダッシュボード自体は停止不要ですが、作業中にWebからプログラムを起動しないでください。モーターの確認は車輪を浮かせるなど教員指定の方法で行います。

PCをPiと同じネットワークへ接続します。SSID・IPの確認は[接続案内](../README.md)を参照してください。
PCのターミナルから、例えばID 04のAPへは `ssh iot@192.168.60.104` で接続します。
ユーザー名は教員指定のものに置き換えます。
VS CodeではRemote - SSH拡張を使って同じ接続先へ接続し、「フォルダーを開く」でPi上の
`~/raspike-spike-demo` を開きます。接続先表示を確認し、リモートの `robot/` と `vision-server/` を
編集・保存してください。VS Codeの統合ターミナルもPi側で開きます。PC上の別コピーやSDK内は編集しません。

## 2. 自分の作業ブランチを作る

```bash
cd ~/raspike-spike-demo
git status
```

知らない変更や他の学生の変更が表示された場合は、教員に確認します。`git restore` や `git reset --hard` で消してはいけません。

未保存の変更がない状態で配布版を更新します。

```bash
git switch main
git pull --ff-only
```

失敗した場合はエラーを教員に見せてください。更新を通すために変更を消さないでください。

初回だけ、このリポジトリ内のcommit作成者を設定します。名前・メールアドレスは教員の指定に従います。GitHubの認証情報ではありません。

```bash
git config user.name "自分の名前"
git config user.email "教員指定のメールアドレス"
```

自分用のブランチを作ります。以下の `s12345` は自分の学籍番号などに置き換え、以後も同じ名前を使います。

```bash
git switch -c student/s12345-pwm
```

同じ作業を再開するときは、`git status` で未保存の変更を確認した後、作成済みのブランチに切り替えます。

```bash
git switch student/s12345-pwm
```

## 3. ソースを編集する

```bash
cd ~/raspike-spike-demo
nano robot/direct_pwm_camera/app.c
```

`nano` は保存が `Ctrl+O` → Enter、終了が `Ctrl+X` です。別のエディタでも構いません。課題によっては `DirectPwmController/` 内のファイルを編集します。対象は課題の指示に従ってください。

## 4. 名前を指定してビルドする

```bash
cd ~/raspike-spike-demo
./scripts/build-robot direct_pwm_camera
```

ラッパーはリポジトリの `robot/direct_pwm_camera/` を直接参照し、SDK workspaceで
`make img=<ソースへの相対パス>` を実行します。ソースコピー、`make app=...`、リンク作成は不要です。
対象ソースとSDKのハッシュによるキャッシュがあれば `asp` を復元します。
ビルド中・実行中は編集やブランチ切替をしないでください。

失敗したらエラーを読んで修正します。古い `asp` が残る可能性があるため、失敗後に
引数なしの `start-robot` や直接 `make start` で実行してはいけません。

## 5. SSHから画像認識とロボットを実行する

現行の黒線ライントレースは `vision-server/vision_server_picamera.py` と
`robot/direct_pwm_camera/` の組合せです。旧 `robot/line_trace_camera/` は使いません。
先に別のSSHターミナルでPythonを前景起動し、開いたままにします。

```bash
cd ~/raspike-spike-demo
./scripts/start-vision
```

このスクリプトは `vision-server/.venv` を使い、既存の同名Pythonプロセスを停止して起動します。
Webで起動したサービスが残っている状態で実行しないでください。
`http://<PiのIP>:8080/` で映像・検出結果を確認します。
マーカー課題では代わりに `vision-server/` で `.venv/bin/python marker_controller.py` を前景起動します。
二つのPythonはカメラとTCPポートを共有するため、同時に起動しません。

ロボット側のSSHターミナルで実行します。

```bash
cd ~/raspike-spike-demo
./scripts/start-robot direct_pwm_camera
```

名前指定の `start-robot` はビルド（またはキャッシュ復元）も行うため、通常はこのコマンドだけで
ビルド・起動できます。§4はビルドだけ確認したい場合の操作です。ビルド失敗時は起動に進みません。
名前指定のビルドから実行までは共通ロックを保持します。Pythonは自動起動されません。

初期状態は一時停止です。フォースセンサーを押して離すと制御開始、次に押して離すと一時停止、
さらに押して離すと再開します。[ポート配置と停止処理の限界](../robot/direct_pwm_camera/README.md)を確認してください。

終了時は機体を一時停止し、ロボットのターミナルで `Ctrl+C` を押してプロンプトと実機停止を確認します。
その後Python側も `Ctrl+C` で終了します。`stop-vision` というスクリプトはありません。
終了しない場合は重ねて起動せず、教員が確認した物理停止手段で対処してください。
Ctrl+CやSSH切断を実機の停止保証として扱わないでください。

Webはsystemd、SSHは前景プロセスで管理するため、開発中はWebから実行・停止しません。
共通ロックはありますがsystemdの排他は手動PythonやSSH起動全体には適用されません。
Webへ切り替える前にSSHで起動したPython・ロボットと待機中の要求を終了します。
ブラウザとの通信断では自動停止しません。Python–C通信失敗の検出時の停止と、
無応答・画像更新停止の未保証事項は[安全上の確認](../README.md#実行管理と安全上の確認)を参照してください。

## 6. 変更をcommitして保存する

ファイルを保存しただけではGitの履歴には残りません。作業の区切りごとに保存します。

```bash
cd ~/raspike-spike-demo
git branch --show-current
git status
git diff
```

自分の作業ブランチで、意図した変更だけであることを確認します。

```bash
git add robot/direct_pwm_camera
git diff --cached
git commit -m "旋回時のモーター出力を調整"
git status
```

メッセージは実際の変更内容に合わせます。別の場所も編集した場合は必要なファイルを追加で `git add` します。

| 操作 | 意味 |
| --- | --- |
| `git add` | 次のcommitに含める変更を選ぶ |
| `git commit` | 選んだ変更をラズパイ内の履歴に保存する |
| `git push` | 履歴をGitHubなどへ送る。学生のラズパイでは行わない |

commitにはインターネット接続やGitHubへの書き込み権限は不要です。ただし、SDカードの故障に備えて次の提出も行ってください。

## 7. bundleを作って提出する

bundleはcommit済みのソースと履歴を一つにまとめた受け渡し用ファイルです。この手順では、自分のブランチに至る履歴全体を含めます。

```bash
cd ~/raspike-spike-demo
git status
git log -5 --oneline
git bundle create ~/s12345-pwm.bundle student/s12345-pwm
git bundle verify ~/s12345-pwm.bundle
```

学籍番号部分は自分のものに置き換えます。ファイルはホームディレクトリに作られます。ソースが消えたりブランチが切り替わったりする操作ではありません。

**未commitの編集はbundleに入りません。`git add` だけの変更も入りません。** 提出する変更をすべてcommitしてから作成します。追加編集した場合はcommit後にbundleを作り直します。別の提出版を残す場合は日付などをファイル名に加えてください。

PC側のターミナルで取得します。

```bash
scp iot@IoT01:~/s12345-pwm.bundle .
```

`iot` は実機のユーザー名、`IoT01` は実機のホスト名またはIPアドレスに置き換えます。最後の `.` はPCの現在のフォルダです。SSH認証は必要ですが、GitHub認証は不要です。USBメモリでコピーしても構いません。

取得した `.bundle` をメールなど教員指定の方法で提出します。本文には氏名・学籍番号・機体番号、ブランチ名、変更内容、動作確認結果、残っている問題を書いてください。bundleは履歴を含むので、パスワードなどをcommitしないでください。

## 8. 配布版へ戻す

変更をすべてcommitし、bundleをPCへ保存した後で行います。

```bash
cd ~/raspike-spike-demo
git status
git switch main
git pull --ff-only
```

変更は自分の作業ブランチに残ります。教員が取り込みを確認するまで、そのブランチとbundleを削除しないでください。配布版に戻すための `git restore` は不要です。

**ブランチを切り替えても、ビルド済みの `asp` や実行中のプログラムは切り替わりません。** 別の版を動かすときは実行を停止し、切り替え後に `./scripts/start-robot direct_pwm_camera` でビルド・起動します。

## 教員向け：PCでの受け取り

以下はGitHubへの書き込み権限を持つ教員が行います。bundleをPC側リポジトリの直下に置いた例です。

```bash
git fetch origin
git bundle verify ./s12345-pwm.bundle
git fetch ./s12345-pwm.bundle student/s12345-pwm:review/s12345-pwm
```

最後の引数は「bundle内のブランチ名:PC側に作るブランチ名」です。この段階ではmainへの統合や作業ファイルの切り替えは行いません。同名ブランチがあれば提出日などを加えた別名を使います。

`verify` はbundleの形式や必要な履歴の有無を検査します。コードの動作や統合時の競合までは検証しません。

```bash
git log --oneline origin/main..review/s12345-pwm
git diff origin/main...review/s12345-pwm
```

PC側の作業を保存してから切り替え、内容と動作を確認します。

```bash
git switch review/s12345-pwm
git push -u origin review/s12345-pwm
```

通常のPR・レビュー手順でmainへ統合します。学生のcommitを運んでいるため、同じ変更の再commitは不要です。

### 補足：差分だけのbundle

```bash
git bundle create ~/s12345-pwm.bundle main..student/s12345-pwm
```

この形式は作業ブランチに含まれ、mainには含まれないcommitを対象にします。受け取り側に元の履歴が必要です。学生向けの基本手順では、前提となる履歴を気にせず扱えるよう `main..` を省略しています。

## 資料の前提

リポジトリの実装確認基準は現行mainのコミット `f9b6188`（2026-10-30静的照合） です。実機試験は行っていません。機体固有の配置・設定、停止動作は教員が実機で確認してください。

- リポジトリ：https://github.com/ise-nituc/raspike-spike-demo
- Git bundle公式資料：https://git-scm.com/docs/git-bundle
