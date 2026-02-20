# API連携ガイド

このドキュメントでは、Withings APIとOura Ring APIの連携方法を説明します。

Google Fit の復旧・運用（`invalid_grant` 対応、再認証、欠損回復）は以下を参照してください。

- [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md)

## 📋 目次

1. [Withings OAuth2 認証](#withings-oauth2-認証)
2. [Oura Ring Personal Token](#oura-ring-personal-token)
3. [トラブルシューティング](#トラブルシューティング)

---

## 🏋️ Withings OAuth2 認証

### 前提条件

1. [Withings Developer Portal](https://developer.withings.com/) でアプリケーションを登録
2. Client IDとConsumer Secretを取得
3. Callback URLを `http://localhost:8501` に設定

### 設定手順

#### 1. secrets.yamlの設定

`config/secrets.yaml` を作成し、以下の情報を入力：

```yaml
withings:
  client_id: "your_withings_client_id"
  consumer_secret: "your_withings_consumer_secret"
```

#### 2. OAuth2認証フロー

1. アプリを起動: `streamlit run app.py`
2. サイドバーで「API連携設定」を選択
3. 「Withings」タブを開く
4. 「🔗 認証URL生成」ボタンをクリック
5. 表示されたURLをブラウザで開く
6. Withingsアカウントでログインし、アクセスを承認
7. リダイレクト後のURLから `code=` の後の文字列をコピー
8. アプリの「認証コード」欄に貼り付け
9. 「✅ 認証実行」をクリック

#### 3. トークンの保存

認証が成功すると、`config/token_withings.json` にアクセストークンとリフレッシュトークンが保存されます。

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 10800,
  "user_id": "...",
  "expires_at": "2026-01-26T22:00:00"
}
```

#### 4. データ取得

1. 「データ取得」メニューを選択
2. 「Withings (体重)」を選択
3. ユーザーIDと取得日数を設定
4. 「📥 Withingsデータ取得」をクリック

### トークンの更新

- トークンは約3時間で期限切れになります
- 自動的にリフレッシュトークンで更新されます
- 手動更新: 「API連携設定」→「🔄 トークン更新」

### 認証解除

「API連携設定」→「🔓 認証解除」で認証情報を削除できます。

---

## 💍 Oura Ring Personal Token

### 前提条件

1. Oura Ringアカウント
2. [Oura Cloud](https://cloud.ouraring.com/) へのアクセス

### 設定手順

#### 1. Personal Tokenの取得

1. [Oura Cloud Personal Access Tokens](https://cloud.ouraring.com/personal-access-tokens) にアクセス
2. 「Create A New Personal Access Token」をクリック
3. トークン名を入力（例: "Health Management System"）
4. 必要なスコープを選択:
   - `daily` (推奨)
   - `heartrate` (オプション)
   - `workout` (オプション)
5. 「Create Token」をクリック
6. 表示されたトークンをコピー（**一度しか表示されません**）

#### 2. secrets.yamlの設定

`config/secrets.yaml` にトークンを追加：

```yaml
oura:
  personal_token: "YOUR_PERSONAL_ACCESS_TOKEN"
```

#### 3. 接続テスト

1. アプリを起動: `streamlit run app.py`
2. 「API連携設定」→「Oura Ring」タブ
3. 「🔍 接続テスト」をクリック
4. ✅ が表示されれば成功

#### 4. データ取得

1. 「データ取得」メニューを選択
2. 「Oura Ring (活動)」を選択
3. ユーザーIDと取得日数を設定
4. 「📥 Ouraデータ取得」をクリック

### 取得できるデータ

- **Activity Score**: 活動スコア
- **Sleep Score**: 睡眠スコア
- **Readiness Score**: コンディションスコア
- **Steps**: 歩数
- **Total Sleep Duration**: 総睡眠時間

---

## 🔧 トラブルシューティング

### Withings関連

#### 「認証エラー」が表示される

- Client IDとConsumer Secretが正しいか確認
- Callback URLが `http://localhost:8501` に設定されているか確認
- 認証コードをコピーする際、余分な空白が入っていないか確認

#### 「Not authenticated」エラー

- 「API連携設定」で認証状態を確認
- トークンが期限切れの場合は再認証

#### データが取得できない

- Withingsアプリで体重データが記録されているか確認
- 取得期間にデータが存在するか確認
- トークンを更新してみる

### Oura Ring関連

#### 「Personal Tokenが設定されていません」

- `config/secrets.yaml` が存在するか確認
- `oura.personal_token` が正しく設定されているか確認
- アプリを再起動

#### データが取得できない

- Oura Ringでデータが同期されているか確認
- Personal Tokenのスコープに `daily` が含まれているか確認
- 取得期間にデータが存在するか確認

### Google Fit関連

#### `invalid_grant: Token has been expired or revoked.`

- トークン失効または同意取り消しで発生します
- Streamlit UI で一度 Google Fit をログアウトし、再認証を実施してください
- 復旧後は `python -m src.main --auto` が `exit code 0` になることを確認してください
- 詳細手順は [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md) を参照

### データベース関連

#### 「テーブルが存在しません」

1. 「データベース管理」メニューを開く
2. 「🔧 テーブル初期化」をクリック
3. 両方のテーブル（weight_data, oura_data）が作成されます

---

## 📊 データ構造

### Withings体重データ (weight_data)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| user_id | TEXT | ユーザーID |
| measured_at | TIMESTAMP | 測定日時 |
| weight_kg | REAL | 体重(kg) |
| raw_data | TEXT | APIレスポンス(JSON) |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |

### Oura活動データ (oura_data)

| カラム | 型 | 説明 |
|--------|-----|------|
| id | INTEGER | 主キー |
| user_id | TEXT | ユーザーID |
| measured_at | TIMESTAMP | 測定日時 |
| activity_score | INTEGER | 活動スコア |
| sleep_score | INTEGER | 睡眠スコア |
| readiness_score | INTEGER | コンディションスコア |
| steps | INTEGER | 歩数 |
| total_sleep_duration | INTEGER | 総睡眠時間(秒) |
| raw_data | TEXT | APIレスポンス(JSON) |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |

---

## 🔒 セキュリティ

- `config/secrets.yaml` と `config/token_*.json` は `.gitignore` に含まれています
- これらのファイルは絶対にGitにコミットしないでください
- Personal Tokenは安全に保管してください
- 本番環境では環境変数の使用を推奨します

---

## 📚 参考リンク

- [Withings API Documentation](https://developer.withings.com/api-reference/)
- [Oura API Documentation](https://cloud.ouraring.com/v2/docs)
- [OAuth 2.0 RFC](https://datatracker.ietf.org/doc/html/rfc6749)
