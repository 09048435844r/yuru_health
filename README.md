# YuruHealth 💚

ゆるく続ける健康管理アプリ。Withings・Oura Ring・Google Fit からデータを自動取得し、Supabase に一元保存。Gemini AI による分析付き。

## ✨ 主な機能

- **Withings 連携** — OAuth2 認証で体重データを自動取得
- **Oura Ring 連携** — 睡眠・活動・コンディションスコアを取得
- **Google Fit 連携** — Samsung Health → Health Connect → Google Fit 経由で歩数・睡眠・体重を取得
- **Supabase (PostgreSQL)** — クラウドDB にデータとOAuth トークンを永続保存
- **Gemini AI 評価** — 蓄積データをもとにユーモア交じりの健康フィードバック
- **天気連携** — OpenWeatherMap + GPS で環境データを記録
- **Streamlit Cloud デプロイ** — スマホからいつでもアクセス可能

## 📁 プロジェクト構成

```
yuru_health/
├── app.py                              # メインUI (モバイル最適化)
├── app_mobile.py                       # モバイル専用UI
├── app_desktop.py                      # デスクトップ専用UI
├── auth/
│   ├── withings_oauth.py               # Withings OAuth2 (Supabase永続化)
│   └── google_oauth.py                 # Google OAuth2 (Supabase永続化)
├── src/
│   ├── database_manager.py             # Supabase クライアント
│   ├── base_fetcher.py                 # データ取得基底クラス
│   ├── withings_fetcher.py             # Withings API
│   ├── fetchers/
│   │   ├── oura_fetcher.py             # Oura Ring API
│   │   ├── google_fit_fetcher.py       # Google Fit API
│   │   └── weather_fetcher.py          # OpenWeatherMap API
│   ├── evaluators/
│   │   ├── base_evaluator.py           # AI評価基底クラス
│   │   └── gemini_evaluator.py         # Gemini AI 評価
│   └── utils/
│       └── secrets_loader.py           # シークレット読み込み (ローカル/Cloud対応)
├── config/
│   ├── settings.yaml                   # アプリ設定 (gitignore)
│   ├── secrets.yaml                    # API認証情報 (gitignore)
│   ├── secrets.example.yaml            # secrets テンプレート
│   └── settings.example.yaml           # settings テンプレート
├── docs/
│   └── API_INTEGRATION.md              # API連携ガイド
├── requirements.txt
├── ROADMAP.md
└── README.md
```

## 🚀 セットアップ

### ローカル環境

```bash
# 1. 依存パッケージのインストール
pip install -r requirements.txt

# 2. 設定ファイルの作成
cp config/secrets.example.yaml config/secrets.yaml
cp config/settings.example.yaml config/settings.yaml
# → 各ファイルに実際のAPIキーを入力

# 3. アプリ起動
streamlit run app.py
```

### Streamlit Cloud

1. GitHub リポジトリを Streamlit Cloud に接続
2. **Secrets** に以下の形式で設定を追加:

```toml
[withings]
client_id = "your_withings_client_id"
client_secret = "your_withings_client_secret"
redirect_uri = "https://your-app.streamlit.app/"

[oura]
personal_token = "your_oura_personal_token"

[gemini]
api_key = "your_gemini_api_key"

[openweathermap]
api_key = "your_openweathermap_api_key"
default_lat = 36.2381
default_lon = 137.9720

[supabase]
url = "https://your-project-id.supabase.co"
key = "your_supabase_anon_key"

[google]
client_id = "your_google_client_id"
client_secret = "your_google_client_secret"
redirect_uris = ["https://your-app.streamlit.app/", "http://localhost:8501/"]
```

### Supabase テーブル

以下のテーブルを Supabase SQL Editor で作成してください:

- `weight_data` — Withings 体重データ
- `oura_data` — Oura Ring データ
- `google_fit_data` — Google Fit データ
- `environmental_logs` — 天気・環境データ
- `oauth_tokens` — OAuth トークン永続化

`oauth_tokens` テーブルの作成SQL:

```sql
CREATE TABLE oauth_tokens (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    token_data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, provider)
);
```

## 🔌 API連携

| サービス | 認証方式 | 取得データ | トークン保存先 |
|---------|---------|-----------|-------------|
| Withings | OAuth 2.0 | 体重 | Supabase |
| Oura Ring | Personal Token | 睡眠・活動・コンディション・歩数 | Secrets |
| Google Fit | OAuth 2.0 | 歩数・睡眠・体重 (Samsung Health経由) | Supabase |
| OpenWeatherMap | API Key | 天気・気温・湿度・気圧 | Secrets |
| Gemini AI | API Key | 健康データ分析 | Secrets |

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

- `config/secrets.yaml` と `config/token_*.json` は `.gitignore` に含まれています
- API には利用制限があります。過度なリクエストは避けてください
- OAuth トークンは Supabase の `oauth_tokens` テーブルに永続保存されます

## 🛠️ 技術スタック

- **Frontend**: Streamlit
- **Database**: Supabase (PostgreSQL)
- **AI**: Google Gemini API
- **Deploy**: Streamlit Community Cloud
- **Language**: Python 3.8+

## 📄 ライセンス

このプロジェクトは個人利用を想定しています。
