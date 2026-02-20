# Secrets & Config Guide

YuruHealth のシークレット/設定の読み込みルールと、環境別の推奨設定です。

---

## 1. 読み込み優先順位

### シークレット (`src/utils/secrets_loader.py`)

1. `config/secrets.yaml`（ローカル）
2. 環境変数（CI/Cloud）で上書き
3. `st.secrets`（Streamlit）フォールバック

補足:
- Supabase URL は正規化されます
- 破損した URL/KEY の一部救済ロジックがあります

### 一般設定 (`src/utils/config_loader.py`)

1. `config/settings.yaml`
2. `st.secrets`（存在する場合のみマージ）

`st.secrets` が未設定でも起動できるよう、未設定時は空辞書にフォールバックします。

---

## 2. ローカル開発

```bash
cp config/secrets.example.yaml config/secrets.yaml
cp config/settings.example.yaml config/settings.yaml
```

- `config/secrets.yaml` は `.gitignore` 対象
- 実値はコミットしない

---

## 3. GitHub Actions

`.github/workflows/periodic_fetch.yml` の env に対応する Secrets を設定します。

最低限:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `OURA_PERSONAL_TOKEN`
- `WITHINGS_CLIENT_ID` / `WITHINGS_CLIENT_SECRET` / `WITHINGS_REDIRECT_URI`
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REDIRECT_URI_*`

---

## 4. Streamlit Cloud

- App Settings の Secrets (TOML) に設定
- `st.secrets` で読み込まれる

---

## 5. よくあるエラーと対処

### `StreamlitSecretNotFoundError`

原因:
- ローカルで `.streamlit/secrets.toml` が無い

対処:
- 現在はフォールバック実装済みのため、`settings.yaml` と `secrets.yaml` があれば起動可能
- それでも出る場合は再起動し、最新コードが反映されているか確認

### `Invalid API key` (Supabase)

原因:
- `SUPABASE_KEY` 不正
- URL/KEY 取り違え

対処:
- `config/secrets.yaml` の `supabase.url` と `supabase.key` を再確認
- CI の GitHub Secrets 値も同様に確認

### OAuth `invalid_grant`

原因:
- リフレッシュトークン失効

対処:
- 再認証を実施
- 参照: [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md)

---

## 6. セキュリティ原則

- APIキー/トークンをコードにハードコードしない
- PR/Issue/ログにトークン生値を貼らない
- 個人環境では `.env` / `config/secrets.yaml`、CI では Secret Manager を使う
