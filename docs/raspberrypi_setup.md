# Raspberry Pi 4 (ARM64) セットアップ手順

この手順は、YuruHealth を Raspberry Pi 4 上の Docker 環境で稼働させるための最短手順です。

## 1. 事前準備

- Raspberry Pi OS (64-bit) を利用する
- Docker / Docker Compose Plugin をインストールする
- 本リポジトリをラズパイに配置する（`.git` を含めて転送推奨）

## 2. 環境変数を準備

1. `dist/.env.production` を開く
2. `your_*` プレースホルダを実値に置き換える
3. Withings / Google Fit を自動実行する場合は、初回のみ UI で OAuth 認証を行い `oauth_tokens` を作成する

## 3. ビルドと起動

```bash
docker compose build --no-cache
docker compose up -d
```

## 4. 稼働確認

- App: `http://<raspberrypi-ip>:8501`
- コンテナ状態:

```bash
docker compose ps
```

- アプリログ:

```bash
docker compose logs -f app
```

- 取得workerログ:

```bash
docker compose logs -f worker
```

## 5. 定常運用コマンド

- 再起動:

```bash
docker compose restart
```

- イメージ再ビルド後に再起動:

```bash
docker compose down
docker compose build
docker compose up -d
```

- 停止:

```bash
docker compose down
```

## 6. トラブルシュート

- OAuth 関連で `strict` エラーが出る場合:
  - `dist/.env.production` の `*_CLIENT_ID`, `*_CLIENT_SECRET`, `*_REDIRECT_URI*` を確認
  - Supabase の `oauth_tokens` に対象 provider の token_data があるか確認
- 取得が止まっている場合:
  - `docker compose logs -f worker` で `python -m src.main --auto` の終了コードを確認
  - 環境変数、ネットワーク疎通、API利用制限を確認
