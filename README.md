# LCStats Relay

LCStatsTracker が `http://localhost:2145/` で公開する統計 JSON を受信し、Google Apps
Script Web App 経由で Google Sheets へ転送する Flet デスクトップアプリです。

受信元は1レスポンスにつき1ペイロードを返して接続を閉じます。
本アプリはペイロードを処理した後に再接続し、次の統計データを待機します。

## 主な動作

1. ローカルの SSE エンドポイントから統計 JSON を受信します。
2. 受信内容を `data/archive/YYYY-MM-DD/` にそのまま保存します。
3. GAS Web App に JSON を POST します。
4. 送信に失敗した場合は `data/queue/` に保存し、バックグラウンドで再送します。

受信データは取得後に受信元からリセットされるため、archive の確定を GAS 送信より先に
行います。同じデータを複数クライアントで安全に取得できる保証はないため、受信クライアントは
本アプリだけにしてください。

## 実行

Python 3.14 と [uv](https://docs.astral.sh/uv/) が必要です。

```powershell
uv sync --locked --all-groups
uv run python -m lcstats_relay
```

画面で以下を指定して「接続開始」を押します。

- SSE URL: 通常は `http://localhost:2145/`
- GAS Web App URL: `https://script.google.com/macros/s/.../exec` の形式の実行 URL

GAS URL は画面上でマスクされ、設定ファイルには保存されません。

## 開発時の検証

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```
