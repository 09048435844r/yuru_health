# YuruHealth 💚

**47 歳の Python 開発者による、エンジニアリングと健康管理の実験場。**

複数のヘルスケアデバイス・API から取得した生データを Supabase (PostgreSQL) に蓄積し、
「ライフログの資産化」を目指すオープンソースプロジェクトです。

> *ゆるく、でもストイックに。データに基づいた健康改善を、エンジニアリングの力で。*

---

## ✨ 主な機能

| 機能 | 説明 |
|------|------|
| **Oura Ring** | 睡眠・活動・コンディションスコアを 7 日分バックフィル |
| **Withings** | OAuth2 で体重データを自動取得 |
| **Google Fit** | Samsung Health → Health Connect 経由で歩数・睡眠・体重 |
| **SwitchBot** | 寝室の CO2・気温・湿度を取得 |
| **OpenWeatherMap** | 気象データ（気温・湿度・気圧）を記録 |
| **Gemini AI** | 生データを横断分析する Deep Insight 機能 |
| **Data Lake** | 全ソースの生 JSON を `raw_data_lake` に一元保存 |
| **GitHub Actions** | 5 分おきに自動取得 (cron) |
| **Streamlit UI** | モバイル最適化ダッシュボード + 記録の足跡グリッド |

## 📁 プロジェクト構成

```
yuru_health/
├── app.py                          # Streamlit メイン UI
├── src/
│   ├── main.py                     # CLI エントリーポイント (GitHub Actions 用)
│   ├── database_manager.py         # Supabase クライアント (hash-guard UPSERT)
│   ├── base_fetcher.py             # Fetcher 基底クラス
│   ├── withings_fetcher.py         # Withings API
│   ├── fetchers/
│   │   ├── oura_fetcher.py         # Oura Ring API
│   │   ├── google_fit_fetcher.py   # Google Fit API
│   │   ├── weather_fetcher.py      # OpenWeatherMap API
│   │   └── switchbot_fetcher.py    # SwitchBot API v1.1
│   ├── evaluators/
│   │   ├── base_evaluator.py       # AI 評価基底クラス
│   │   └── gemini_evaluator.py     # Gemini AI 評価
│   └── utils/
│       └── secrets_loader.py       # シークレット読み込み (env → YAML → st.secrets)
├── auth/
│   ├── withings_oauth.py           # Withings OAuth2 (Supabase 永続化)
│   └── google_oauth.py             # Google OAuth2 (Supabase 永続化)
├── config/
│   ├── secrets.example.yaml        # secrets テンプレート
│   └── settings.example.yaml       # settings テンプレート
├── .github/workflows/
│   └── periodic_fetch.yml          # 5 分おき自動取得
├── .env.example                    # 環境変数テンプレート
├── requirements.txt
└── README.md
```

## 🚀 セットアップ

### 1. ローカル開発

```bash
git clone https://github.com/09048435844r/yuru_health.git
cd yuru_health
pip install -r requirements.txt

# 設定ファイルを作成して API キーを入力
cp config/secrets.example.yaml config/secrets.yaml
cp config/settings.example.yaml config/settings.yaml

# Streamlit UI を起動
streamlit run app.py

# CLI で手動取得
python -m src.main --auto
```

### 2. 環境変数 (推奨)

YAML の代わりに環境変数でシークレットを管理できます。`.env.example` を参照してください。

```bash
cp .env.example .env
# .env に実際の値を入力
```

**必要な環境変数一覧:**

| 変数名 | 説明 |
|--------|------|
| `SUPABASE_URL` | Supabase プロジェクト URL |
| `SUPABASE_KEY` | Supabase anon key |
| `OURA_PERSONAL_TOKEN` | Oura Ring パーソナルトークン |
| `GEMINI_API_KEY` | Google Gemini API キー |
| `GEMINI_MODEL_NAME` | Gemini モデル名 (default: `gemini-1.5-flash`) |
| `OPENWEATHERMAP_API_KEY` | OpenWeatherMap API キー |
| `OPENWEATHERMAP_DEFAULT_LAT` | デフォルト緯度 |
| `OPENWEATHERMAP_DEFAULT_LON` | デフォルト経度 |
| `WITHINGS_CLIENT_ID` | Withings OAuth client ID |
| `WITHINGS_CLIENT_SECRET` | Withings OAuth client secret |
| `WITHINGS_REDIRECT_URI` | Withings リダイレクト URI |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI_CLOUD` | Google リダイレクト URI (Cloud) |
| `GOOGLE_REDIRECT_URI_LOCAL` | Google リダイレクト URI (localhost) |
| `SWITCHBOT_TOKEN` | SwitchBot API トークン |
| `SWITCHBOT_SECRET` | SwitchBot API シークレット |
| `SWITCHBOT_DEVICE_ID` | SwitchBot デバイス ID |

### 3. GitHub Actions (自動取得)

リポジトリの **Settings → Secrets and variables → Actions** に上記の環境変数を登録すると、
5 分おきに全 Fetcher が自動実行されます。手動実行は Actions タブの **"Run workflow"** から。

### 4. Streamlit Cloud

GitHub リポジトリを Streamlit Cloud に接続し、**Secrets** に TOML 形式で設定を追加:

```toml
[supabase]
url = "https://your-project-id.supabase.co"
key = "your_supabase_anon_key"

[oura]
personal_token = "your_oura_personal_token"

[gemini]
api_key = "your_gemini_api_key"

[openweathermap]
api_key = "your_openweathermap_api_key"
default_lat = 35.6762
default_lon = 139.6503

[withings]
client_id = "your_withings_client_id"
client_secret = "your_withings_client_secret"
redirect_uri = "https://your-app.streamlit.app/"

[google]
client_id = "your_google_client_id"
client_secret = "your_google_client_secret"
redirect_uris = ["https://your-app.streamlit.app/", "http://localhost:8501/"]

[switchbot]
token = "your_switchbot_token"
secret = "your_switchbot_secret"
device_id = "your_switchbot_device_id"
```

### 5. Supabase テーブル

以下のテーブルを Supabase SQL Editor で作成してください:

```sql
-- OAuth トークン永続化
CREATE TABLE oauth_tokens (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    token_data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, provider)
);

-- Data Lake (全ソースの生データ)
CREATE TABLE raw_data_lake (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT unique_raw_data_v2 UNIQUE (user_id, fetched_at, source, category)
);

-- その他: weight_data, oura_data, google_fit_data, environmental_logs
-- (スキーマは src/database_manager.py の insert メソッドを参照)
```

## 🔌 API 連携

| サービス | 認証方式 | 取得データ | トークン保存先 |
|---------|---------|-----------|-------------|
| Oura Ring | Personal Token | 睡眠・活動・コンディション・歩数 | 環境変数 |
| Withings | OAuth 2.0 | 体重 | Supabase |
| Google Fit | OAuth 2.0 | 歩数・睡眠・体重 (Samsung Health 経由) | Supabase |
| SwitchBot | API Token + HMAC | CO2・気温・湿度 | 環境変数 |
| OpenWeatherMap | API Key | 天気・気温・湿度・気圧 | 環境変数 |
| Gemini AI | API Key | 健康データ Deep Insight 分析 | 環境変数 |

## 🏗️ アーキテクチャ

```
[Oura / Withings / Google Fit / SwitchBot / Weather]
        │
        ▼
  src/main.py --auto  ← GitHub Actions (*/5 * * * *)
        │
        ▼
  DatabaseManager.save_raw_data()
    ├─ SHA-256 hash-guard (重複スキップ)
    └─ INSERT with fetched_at timestamp
        │
        ▼
  Supabase (raw_data_lake)
        │
        ▼
  app.py (Streamlit UI)
    ├─ 記録の足跡グリッド
    ├─ 今日のメトリクス
    └─ Gemini AI Deep Insight
```

## 🔌 拡張方法

`src/base_fetcher.py` を継承して新しいデータソースを追加できます:

```python
from src.base_fetcher import BaseFetcher

class NewServiceFetcher(BaseFetcher):
    def authenticate(self) -> bool:
        pass

    def fetch_data(self, user_id, start_date=None, end_date=None):
        pass
```

## 📝 注意事項

- `config/secrets.yaml` と `.env` は `.gitignore` に含まれています — **コミットされません**
- API には利用制限があります。過度なリクエストは避けてください
- OAuth トークンは Supabase の `oauth_tokens` テーブルに永続保存されます
- GitHub Actions の無料枠: Public リポジトリは無制限、Private は月 2,000 分

## 🛠️ 技術スタック

- **Language**: Python 3.10
- **Frontend**: Streamlit
- **Database**: Supabase (PostgreSQL)
- **AI**: Google Gemini API
- **CI/CD**: GitHub Actions (5 分間隔 cron)
- **Deploy**: Streamlit Community Cloud

## 📄 ライセンス

MIT License
