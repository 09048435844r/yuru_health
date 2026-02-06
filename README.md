# 健康管理システム (Yuru Health)

WSL2/Linux環境で動作する健康管理システム。Withings APIとOura Ring APIからデータを取得し、一元管理できます。

## 📁 プロジェクト構成

```
yuru_health/
├── app.py                          # Streamlit UI
├── config/
│   ├── settings.yaml               # 環境設定ファイル
│   ├── secrets.yaml                # API認証情報 (gitignore)
│   └── token_withings.json         # Withingsトークン (自動生成)
├── auth/
│   └── withings_oauth.py           # Withings OAuth2認証
├── src/
│   ├── database_manager.py        # DB切り替え機能
│   ├── base_fetcher.py             # 基底クラス
│   ├── withings_fetcher.py         # Withings API実装
│   └── fetchers/
│       └── oura_fetcher.py         # Oura Ring API実装
├── docs/
│   └── API_INTEGRATION.md          # API連携ガイド
├── data/                           # SQLiteデータベース保存先
├── requirements.txt
└── README.md
```

## 🚀 セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 設定ファイルの作成

#### 基本設定 (settings.yaml)

`config/settings.yaml` を編集して環境を設定：

```yaml
env: "local"  # "local" (SQLite) または "production" (MySQL)
```

#### API認証情報 (secrets.yaml)

`config/secrets.yaml` を作成し、API認証情報を設定：

```yaml
withings:
  client_id: "your_withings_client_id"
  consumer_secret: "your_withings_consumer_secret"

oura:
  personal_token: "your_oura_personal_token"
```

**詳細な設定方法は [API連携ガイド](docs/API_INTEGRATION.md) を参照してください。**

### 3. データベースの初期化

アプリを起動後、サイドバーから「データベース管理」→「テーブル初期化」を実行してください。

## 🎯 使い方

### アプリケーションの起動

```bash
streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

### 基本操作

1. **API連携設定**: 
   - Withings OAuth2認証を実行
   - Oura Ring Personal Tokenを設定
   
2. **データ取得**: 
   - Withings APIから体重データを取得
   - Oura Ring APIから活動・睡眠データを取得
   
3. **データ表示**: 
   - 体重推移グラフとテーブルを確認
   - 活動スコア・睡眠スコアの推移を確認
   
4. **DB管理**: 
   - テーブル初期化や接続テストを実行

## 🔧 データベース切り替え

### ローカル環境 (SQLite)

```yaml
env: "local"
database:
  local:
    type: "sqlite"
    path: "data/health_data.db"
```

### 本番環境 (MySQL)

```yaml
env: "production"
database:
  production:
    type: "mysql"
    host: "your_mysql_host"
    port: 3306
    database: "health_management"
    user: "your_mysql_user"
    password: "your_mysql_password"
```

## 📊 データベーススキーマ

### weight_data テーブル (Withings)

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER/INT | 主キー |
| user_id | TEXT/VARCHAR | ユーザーID |
| measured_at | TIMESTAMP/DATETIME | 測定日時 |
| weight_kg | REAL/DECIMAL | 体重(kg) |
| raw_data | TEXT | APIレスポンス(JSON) |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |

### oura_data テーブル (Oura Ring)

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | INTEGER/INT | 主キー |
| user_id | TEXT/VARCHAR | ユーザーID |
| measured_at | TIMESTAMP/DATETIME | 測定日時 |
| activity_score | INTEGER/INT | 活動スコア |
| sleep_score | INTEGER/INT | 睡眠スコア |
| readiness_score | INTEGER/INT | コンディションスコア |
| steps | INTEGER/INT | 歩数 |
| total_sleep_duration | INTEGER/INT | 総睡眠時間(秒) |
| raw_data | TEXT | APIレスポンス(JSON) |
| created_at | TIMESTAMP | 作成日時 |
| updated_at | TIMESTAMP | 更新日時 |

## 🔌 API連携機能

### Withings API (OAuth2)

- **認証方式**: OAuth 2.0
- **取得データ**: 体重測定データ
- **自動トークン更新**: 対応
- **詳細**: [API連携ガイド](docs/API_INTEGRATION.md#withings-oauth2-認証)

### Oura Ring API (Personal Token)

- **認証方式**: Personal Access Token
- **取得データ**: 
  - 活動スコア
  - 睡眠スコア
  - コンディションスコア
  - 歩数
  - 睡眠時間
- **詳細**: [API連携ガイド](docs/API_INTEGRATION.md#oura-ring-personal-token)

## 🔌 拡張方法

### 新しいデータソースの追加

1. `src/base_fetcher.py` を継承した新しいクラスを作成
2. `fetch_data()` と `authenticate()` メソッドを実装
3. `config/settings.yaml` に設定を追加

例：
```python
from src.base_fetcher import BaseFetcher

class NewServiceFetcher(BaseFetcher):
    def authenticate(self) -> bool:
        # 認証処理
        pass
    
    def fetch_data(self, user_id: str, start_date=None, end_date=None):
        # データ取得処理
        pass
```

## 📝 注意事項

- **セキュリティ**: 
  - `config/secrets.yaml` と `config/token_*.json` は `.gitignore` に含まれています
  - これらのファイルは絶対にGitにコミットしないでください
  - 本番環境では環境変数の使用を推奨します
- **MySQL使用時**: `pymysql` パッケージが必要です（requirements.txtに含まれています）
- **WSL2環境**: Linux標準のパス区切り(`/`)を使用しています
- **API制限**: 各APIには利用制限があります。過度なリクエストは避けてください

## 🛠️ 開発環境

- Python 3.8+
- WSL2 (Ubuntu推奨)
- 本番環境: さくらインターネット (Linux)

## 📄 ライセンス

このプロジェクトは個人利用を想定しています。
