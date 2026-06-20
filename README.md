# LCStats Relay

LCStatsTracker が `http://127.0.0.1:2145/` で公開する統計 JSON を受信し、Google Apps
Script Web App 経由で Google Sheets へ転送する Flet デスクトップアプリです。

受信元は1レスポンスにつき1ペイロードを返して接続を閉じます。
本アプリはペイロードを処理した後に再接続し、次の統計データを待機します。

## 主な動作

1. ローカルの SSE エンドポイントから統計 JSON を受信します。
2. 登録済みの出力面へ順に配送します。
3. 標準では以下の2つの出力面を使います。
   - ローカル保存: 受信内容を `data/archive/YYYY-MM-DD/` にそのまま保存します。
   - Google Sheets: GAS Web App に JSON を POST します。
4. 再送可能な出力面が失敗した場合は `data/queue/` に保存し、バックグラウンドで再送します。

ローカル保存は必須出力面です。
ここで失敗した場合、後続の出力面には配送しません。
受信データは取得後に受信元からリセットされるため、同じデータを複数クライアントで安全に取得できる保証はありません。
受信クライアントは本アプリだけにしてください。

出力実装、出力別状態表示、GAS認証は分離されています。
第3の出力面を追加する場合は、新しい出力実装を登録し、UIは出力別状態をそのまま表示します。

## 実行

Python 3.14 と [uv](https://docs.astral.sh/uv/) が必要です。

```powershell
uv sync --locked --all-groups
uv run python -m lcstats_relay
```

画面で以下を指定して「接続開始」を押します。

- SSE URL: 通常は `http://127.0.0.1:2145/`
- GAS Web App URL: `https://script.google.com/macros/s/.../exec` の形式の実行 URL
- GAS Token: GAS側でtoken検証している場合のtoken値

既定のSSE URLは `localhost` ではなく `127.0.0.1` です。
これは `localhost` の名前解決でIPv6/IPv4の接続試行が発生し、環境によって接続開始が遅くなることを避けるためです。
互換性のため `http://localhost:2145/` も入力できますが、受信時は `Host` ヘッダーを維持したままIPv4ループバックへ接続します。

GAS Token はURLに含めず、Token欄に入力してください。
GAS Token は画面上でマスクされ、設定ファイルには保存されません。

## 開発時の検証

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```
