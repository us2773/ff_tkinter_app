# ff_tkinter_app

動画を撮影・選択して疲労分析APIへ送り、受信したJSON本文と処理ログを表示する、Windows向けの最小構成クライアントです。

- 「撮影する（10秒）」：カメラの準備後、10秒間撮影し、保存・カメラ解放後に自動送信します。プレビュー・音声録音はありません。
- 「動画を選択して送信」：ファイル選択ダイアログでMP4・MOVを選ぶと送信します。キャンセルした場合は送信しません。
- 「サンプル動画を送信」：設定した動画を送信します。
- 大きなログ欄に、時刻付きの進捗・失敗理由・HTTPステータス・受信本文を追記します。スクロール、選択、Ctrl+A、Ctrl+Cに対応します。

撮影・通信中も画面を操作・再描画できます。処理中は3つのボタンを無効化します。失敗後は再度ボタンから実行できます。自動再送は行いません。

## 準備（Windows PowerShell）

Python 3.11以上とTkinter、カメラが必要です。Python公式のWindows版には通常Tkinterが含まれます。
リポジトリを取得し、そのディレクトリで実行してください。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.example.toml config.local.toml
```

`config.local.toml`の`base_url`を、起動済みAPIのアドレスに変更します。
Tailscaleで接続する場合は、サーバのTailscale IPまたは名前を指定します。

```toml
[api]
base_url = "http://100.x.y.z:8000"
connect_timeout_seconds = 5
response_timeout_seconds = 120

[camera]
index = 0

[files]
sample_video = "samples/sample.mp4"
recordings_directory = "recordings"
```

`base_url`にはパスやクエリを含めません。設定したホストへの直接接続を使用します。
相対パスは**設定ファイルがあるディレクトリ**を基準に解決します。
Windowsの絶対パスは`"C:/Users/example/Videos/sample.mp4"`のように`/`で区切るか、TOMLのリテラル文字列（単一引用符）を使ってください。

用意したサンプル動画を`samples/sample.mp4`に置くか、`sample_video`に既存動画の場所を指定してください。
動画は同梱していません。未配置の場合もアプリは起動でき、サンプル送信時に理由を表示します。
撮影動画、サンプル動画、個人用設定はGitの追跡対象から除外しています。

## 起動

```powershell
.\.venv\Scripts\python.exe -m ff_tkinter_app
```

別の設定ファイルを使う場合：

```powershell
.\.venv\Scripts\python.exe -m ff_tkinter_app --config C:/path/to/config.local.toml
```

撮影動画は`recordings_directory`に日時と識別子を付けて保存し、送信後も残します。
撮影に失敗・終了操作で中止した未完成の動画は削除し、送信しません。
ウィンドウを閉じると、撮影を中止してカメラを解放してから終了します。
通信中の場合は通信終了または設定したタイムアウトまで終了を待ちます。タイムアウトはソケット通信の待ち時間です。

## 接続するAPI

[fatigue-analysis-kitのサンプルAPI](https://github.com/us2773/fatigue-analysis-kit/tree/codex/sample-analysis-api/api)に合わせています。
サーバ側の起動手順は同ディレクトリのREADMEを参照してください。APIは別途起動する必要があります。

| 項目 | 内容 |
| --- | --- |
| リクエスト | `POST /v1/analyses?pipeline=daily` |
| 本文 | 動画バイナリを直接ストリーミング送信（multipart・base64は使用しない） |
| Content-Type | MP4：`video/mp4`、MOV：`video/quicktime` |
| レスポンス | HTTPステータスと本文全体を表示 |

HTTP 400・409・500などでも本文を表示し、JSON以外のエラーページもそのまま確認できます。
JSONはインデント付きで表示し、日本語、`null`、未知のキーも含めて確認できます。JSONとして解析できない本文はそのまま表示します。
アプリの「受信完了」はHTTP通信の完了を指します。分析結果の`status`や特徴量別エラーは本文で確認してください。
`X-Analysis-Mode`ヘッダーがある場合はログに表示します。サンプルAPIの応答は実分析の結果ではありません。

## 3層構成

| 層 | ディレクトリ | 責務 |
| --- | --- | --- |
| 表示層 | `src/ff_tkinter_app/presentation/` | Tkinter、ファイル選択、バックグラウンド処理と表示の連携 |
| アプリケーション層 | `src/ff_tkinter_app/application/` | 撮影→送信の手順、3種類の入力の共通化、外部処理のインターフェース |
| 外部処理層 | `src/ff_tkinter_app/infrastructure/` | OpenCV撮影・保存、標準ライブラリによるHTTP通信 |

`main.py`で設定を読み、外部処理の実装をアプリケーション層に渡します。
アプリケーション層はTkinter・OpenCV・HTTPの具体的な実装を参照しません。
ワーカースレッドからはイベントをキューに渡し、画面更新はTkinterのメインスレッドだけで行います。
撮影は単調増加時計で10秒を計測し、30fpsのMP4へ保存します。カメラのフレーム取得が遅い場合は直前フレームを補って再生時間を保ちます。
実際の停止タイミングはカメラドライバのフレーム読み取り時間の影響を受けます。

## テスト

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ローカルHTTPサーバで動画の生バイナリ・URL・ヘッダー・エラー本文の保持を確認します。
代替カメラと時計で10秒停止、保存とカメラ解放、失敗時の削除・送信抑止を確認します。
GUIのテストは画面を表示せず、ボタンからの非同期処理・ログ表示・失敗後の復帰を確認します。
実カメラ、実サーバ、Tailscale経由の接続は、それぞれの環境で確認してください。
