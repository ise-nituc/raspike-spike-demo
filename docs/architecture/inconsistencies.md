# 実装と文書の不整合

基準コミット・調査限界は[current-state.md](current-state.md)参照。行番号は基準コミットのもの。P0は体験運用・安全性の判断前に解決、P1は手順統一前に解決、P2は文書の役割整理。本PRでは既存文書や実装を修正しない。

## 1. 照合結果

| ID / 優先 | 記述・場所 | 実装の根拠と差分 | 提案する扱い |
| --- | --- | --- | --- |
| D01 / P1 | `robot/direct_pwm_camera/README.md` L6–8: workspaceへコピーしmake app= | `scripts/build-robot` L93–99はrobot/の相対パスをmake img=に渡す | 正式手順を名前指定ラッパーへ統一し、コピー例を廃止 |
| D02 / P1 | `vision-server/README.md` L39–57、L151–169: robot/appdirリンク前提、start時にリンク作成 | build-robotはリンクを作らず、通常アプリはrobot/を直接参照。appdirは互換分岐 | Python READMEからロボット汎用手順を切り出し、正式手順へリンク |
| D03 / P2 | 同README L1–94とL95以降に見出し・手順が重複 | 後半だけ詳しい機能説明もあり、単純な全文片側削除では情報を失う | 共通部を統合し固有説明を残す。単純GETの2項目応答と現行Cの要求/応答を区別 |
| D04 / P0 | `README.md` L49: 画像認識→カメラ・ライントレース | programs.jsonは旧line-trace-cameraを非互換と明記。現行visionはPWM応答、旧VisionClientは空白区切りfloat | 現行組合せをdirect_pwm_cameraへ明記し旧版を分離 |
| D05 / P0 | `README.md` L63–64: 対応Pythonは依存関係で自動起動 | direct-pwm unitにRequiresなし。旧line-trace unitだけ現行visionをRequires | Pythonを先に選ぶ実手順を明示。旧unit依存を別実装PRで再検討 |
| D06 / P1 | `docs/student-development-guide.md` §4–5: SDK直接make | ソースの正本は一致するがflock・キャッシュ・状態通知を迂回。Webとの混用禁止は人の注意に依存 | 正式入口をラッパーへ集約。直接makeは教員の診断用に限定 |
| D07 / P1 | 同資料 §5・§8、direct_pwm README L14–29: ビルドと既存aspの起動 | 古いaspへの注意自体は正しい。分離した二操作間には別ビルドが入り得る | 名前指定の一続きの実行を標準にし、成果物照合を今後追加 |
| D08 / P0 | `robot/ocan2026/README.md` L19、L32、L42–45: smooth_traceが使える | LineTracer.h L35に宣言、LineTracer.c L87–94では実装全体がコメント | 当面教材から利用可能と案内しない。実装復帰の可否は別PRでビルド・実機評価 |
| D09 / P0 | 同README L5・L17: left/rightを単独で試す体験 | LineTracer.c L12のsteering初期値0、L53–64のblack/whiteで更新しL77–84で参照。単独left/rightは初期状態で左右同出力 | 課題例を実装に合わせるかAPIを別PRで整理。旋回・停止の期待を車輪浮上で検証 |
| D10 / P1 | `README.md` L27のAP名raspike-ap | setupのSSIDはiotNN。raspike-apは接続プロファイル名 | SSID/接続名/ホスト名/IPを区別。筐体にIDとURL表示 |
| D11 / P2 | `scripts/README.md`はclone setupと再起動後確認が中心 | クローン設定の説明は概ねsetupに一致するが、build/start/stopの一覧や引数既定値・cache説明がない | 保守用索引と通常操作入口を追加。配布更新は未保存変更の確認を前提化 |
| D12 / P2 | `docs/dashboard-proposal.md` §1–3: raspike.local:80、nginx、gunicorn、専用ユーザー | 現行はFlask :8082、install実行ユーザー。nginx導入はない | 既存の「初期設計案」注記を維持し、現行構成との差分表を追加 |
| D13 / P2 | 同 §5: 事前ビルド物のみ起動、TERM→KILL | 現行は開始時build/cache、ロボットunitは即SIGKILL | 初期案と現行仕様を分離。安全停止方式は実機検証後に判断 |
| D14 / P1 | 同 §3 AP例: 校内Wi-Fi自動接続無効化、SSID例 | 現行setupは校内プロファイルを変更しない。SSIDはiotNN | 初期案のコマンドを現行設定手順として使わない |
| D15 / P0 | READMEの「停止」と画面のready/runningから実機停止・準備完了を推測し得る | dashboard/app.py stateとstart-robotは状態ファイル/プロセスを表示。モーター確認や成果物同一性の計測ではない | 表示の意味と未確認を明記。停止判定・成果物IDを次段階で設計 |

相対パスの`make img=`、Git branch/bundle、ビルド失敗後の旧asp注意は学生資料の有用な現行説明であり、コピー方式の旧記述と一括で廃止する必要はない。VS Codeの接続・保存先は未整備で、Remote SSHでPi上の同じrobot/を開く説明を追加する。

## 2. 文書の不一致とは別の設計課題

| ID | 観測できる実装 | 含意・次の確認 |
| --- | --- | --- |
| A01 | start-robotに名前なし既存asp起動、build-robotにappdir互換分岐が残る | ソース正本の統一は通常アプリでは既に可能。互換経路を通常教材から外し、廃止は影響調査後 |
| A02 | build cacheは対象全ファイルとSDKハッシュ、成果物ダイジェスト・ツールチェーン識別なし | README変更でもmiss。コンパイラ更新で必ず失効する保証はない。完全な再現ビルドと呼ばない |
| A03 | flockはラッパー間、Conflictsはunit間だけ | 直接make/手動Pythonは別管理。WebとCLIの排他を共通入口へ集約 |
| A04 | ブラウザの定期状態取得はあるが走行lease失効処理なし | Wi-Fi断とPi内TCP断を区別。ブラウザ断停止は未実装 |
| A05 | 通信失敗時stopはあるがCのrecv期限が明示されず、最新PWMの鮮度失効も見当たらない | ハング時停止時間は保証できない。安全監視の実機試験が必要 |
| A06 | 固定sudoコマンドは相対./aspを実行、Web/robot unitは通常同一ユーザー | 任意Cを許すWeb編集を同じ権限のまま追加できない。引数制限だけではCの能力を制限できない |
| A07 | ocan2026 main_taskは開始時のみforce待ち | 再押下pauseはdirect_pwm_cameraと同じではない。初学者の無限ループを既存APIだけで安全化できない |
| A08 | start-demoは既存asp、stop-demoはvisionのみ停止 | デモを一括管理する名前に対して対象/停止範囲が限定的。通常手順をsystemdへ寄せる |

## 3. 文書の役割分担（次段階の提案）

| 文書 | 正式に維持する役割 |
| --- | --- |
| README.md | 初めての接続・デモ起動停止、正しい組合せ、他手順への入口 |
| scripts/README.md | 教員の初期設定・clone・復旧、スクリプトの引数/副作用/互換経路、設定後の確認 |
| docs/student-development-guide.md | 通常開発の正本・Remote SSH/エディタ・共通入口・Git/bundle・提出復旧 |
| vision-server/README.md | Python依存、画像認識の機能・設定・ポート・TCPプロトコル。ビルド手順はリンク |
| robot/direct_pwm_camera/README.md | C側ポート配置、pause/停止条件、現行プロトコルと互換範囲 |
| robot/ocan2026/README.md | 40分教材、編集範囲、検証済み関数、講師準備・初期/完成版復元 |
| docs/dashboard-proposal.md | 歴史的な初期案。現行手順の正本にしない |
| docs/architecture/ | 調査時点の証拠・設計判断・段階移行。採用後も未実装項目を正式仕様と混同しない |

汎用ビルド/実行手順は学生資料へ集約し、各READMEはそこへリンクする。SDKの詳細は版を記録して保守資料へ置く。PowerPoint教材は内容未確認として棚卸し対象に含める。今回の追加文書によって既存の誤記が修正済みになったとは扱わない。
