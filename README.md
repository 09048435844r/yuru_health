# YuruHealth 💚

**健康オタクの Python 開発者による、エンジニアリングと健康管理の実験場。**

複数のヘルスケアデバイス・API から取得した生データを Supabase (PostgreSQL) に蓄積し、
「ライフログの資産化」を目指すオープンソースプロジェクトです。

> *ゆるく、でもストイックに。データに基づいた健康改善を、エンジニアリングの力で。*

---

## ✨ Current Features

### データ収集

| ソース | 取得データ | 認証方式 |
|--------|-----------|---------|
| **Oura Ring** | 睡眠・活動・コンディションスコア (7 日分バックフィル) | Personal Token |
| **Withings** | 体重 | OAuth 2.0 |
| **Google Fit** | 歩数・睡眠・体重 (Samsung Health → Health Connect 経由) | OAuth 2.0 |
| **SwitchBot** | 寝室の CO2・気温・湿度 | API Token + HMAC |
| **OpenWeatherMap** | 天気・気温・湿度・気圧 | API Key |

### Phase 1 完了機能

| 機能 | 説明 |
|------|------|
| **高密度データ取得** | GitHub Actions による 15 分間隔の自動フェッチ (cron: `3,18,33,48 * * * *`) |
| **インテリジェント・ハッシュガード** | `_strip_volatile()` でタイムスタンプ系メタデータ (`dt`, `timestamp`, `cod` 等) を除外した SHA-256 比較による重複排除 |
| **JST タイムゾーン同期** | 全コンポーネント (`database_manager`, `fetchers`, `app.py`, `main.py`) における `datetime.now(JST)` への完全統一 |
| **recorded_at 自動補完** | payload 内の `dt` / `timestamp` / `date` から `recorded_at` を導出。見つからなければ JST 現在時刻をフォールバック |
| **モバイル最適化 UI** | Galaxy Z Fold7 等に対応した Sticky カラム付き横スクロール HTML テーブル |
| **Sparklines** | SwitchBot / Weather の 24h 気温推移を SVG ミニ折れ線グラフで表示 |
| **サマリーバッジ** | Oura (睡眠/活動/準備スコア)、Withings (体重)、Google Fit (歩数/睡眠) をカラーバッジで表示 |
| **Gemini AI Deep Insight** | 生データを横断分析する AI 機能 |
| **Raw Data View** | サイドバーのチェックボックスで `raw_data_lake` 最新 100 件を表示 |
| **Data Lake** | 全ソースの生 JSON を `raw_data_lake` に一元保存 |

## 📁 プロジェクト構成

```
yuru_health/
├── app.py                          # Streamlit メイン UI (モバイル最適化)
├── src/
│   ├── main.py                     # CLI エントリーポイント (GitHub Actions 用)
│   ├── database_manager.py         # Supabase クライアント
│   │                               #   - hash-guard (SHA-256 重複排除)
│   │                               #   - _strip_volatile() (メタデータ除外)
│   │                               #   - _extract_recorded_at() (タイムスタンプ導出)
│   │                               #   - get_data_arrival_rich() (Sparkline/Badge データ)
│   ├── base_fetcher.py             # Fetcher 抽象基底クラス
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
│       ├── secrets_loader.py       # シークレット読み込み (env → YAML → st.secrets)
│       └── sparkline.py            # SVG Sparkline + Badge + HTML テーブル生成
├── auth/
│   ├── withings_oauth.py           # Withings OAuth2 (Supabase 永続化)
│   └── google_oauth.py             # Google OAuth2 (Supabase 永続化)
├── config/
│   ├── secrets.example.yaml        # secrets テンプレート
│   └── settings.example.yaml       # settings テンプレート
├── .github/workflows/
│   └── periodic_fetch.yml          # 15 分間隔自動取得 (ラウンド数回避 cron)
├── .env.example                    # 環境変数テンプレート
├── requirements.txt
└── README.md
```

## 📚 運用ドキュメント

- [Docs Index](docs/README.md)
- [API連携ガイド](docs/API_INTEGRATION.md)
- [Google Fit OAuth 復旧・運用 Runbook](docs/GOOGLE_FIT_OAUTH_RUNBOOK.md)
- [Operations Playbook](docs/OPERATIONS_PLAYBOOK.md)
- [Secrets & Config Guide](docs/SECRETS_CONFIGURATION.md)

## 🏗️ アーキテクチャ

```
[Oura / Withings / Google Fit / SwitchBot / Weather]
        │
        ▼
  src/main.py --auto  ← GitHub Actions (cron: 3,18,33,48 * * * *)
        │
        ▼
  DatabaseManager.save_raw_data()
    ├─ _strip_volatile()  → メタデータ除外
    ├─ _payload_hash()    → SHA-256 比較 (重複スキップ)
    ├─ _extract_recorded_at() → payload からタイムスタンプ導出
    └─ INSERT (fetched_at=JST now, recorded_at=導出値)
        │
        ▼
  Supabase (raw_data_lake)
        │
        ▼
  app.py (Streamlit UI)
    ├─ 記録の足跡 (Sparklines + Badges HTML テーブル)
    ├─ 今日のメトリクス
    ├─ Gemini AI Deep Insight
    └─ Raw Data View (サイドバー)
```

### ハッシュガードの仕組み

```
新規 payload → _strip_volatile() で変動キーを除外
                    │
                    ▼
              _payload_hash() → SHA-256
                    │
                    ▼
         既存の最新レコードのハッシュと比較
            │                    │
         一致 → SKIP          不一致 → INSERT
     (ログ出力)           (fetched_at + recorded_at 付き)
```

**除外キー (`_VOLATILE_KEYS`):**
`dt`, `t`, `time`, `timestamp`, `ts`, `server_time`, `fetched_at`, `recorded_at`, `updated_at`, `created_at`, `cod`

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
15 分間隔で全 Fetcher が自動実行されます。手動実行は Actions タブの **"Run workflow"** から。

> **Note:** cron はラウンド数 (`:00`, `:05`) を避けた `3,18,33,48` 分に設定し、
> GitHub Actions のスケジューリング遅延を軽減しています。

> **Fail-fast運用:** OAuthトークン失効などの認証異常が発生した場合、`python -m src.main --auto` は
> 非ゼロ終了コードで失敗し、サイレント成功しない設計です。復旧手順は
> [Google Fit OAuth 復旧・運用 Runbook](docs/GOOGLE_FIT_OAUTH_RUNBOOK.md) を参照してください。

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
    recorded_at TIMESTAMPTZ NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    CONSTRAINT unique_raw_data_v2 UNIQUE (user_id, fetched_at, source, category)
);

-- その他: weight_data, oura_data, google_fit_data, environmental_logs
-- (スキーマは src/database_manager.py の insert メソッドを参照)
```

## 🧪 開発・テスト (Development & Testing)

### 手動テストの実行

```bash
pytest
```

ローカルでの開発時は、実装変更後に `pytest` を実行して回帰がないことを確認してください。

### 自動テストの仕様（pre-commit hook）

- Git の `pre-commit` フック（`.git/hooks/pre-commit`）で、`git commit` 時に自動で `pytest` を実行します。
- テストが失敗した場合は `exit 1` でコミットを中止します。
- テストが成功した場合のみ、そのままコミットが続行されます。

### 現在のテスト範囲

- 現在は `ffmpeg_renderer.py` のパス処理など、基盤ロジックの単体テストを中心に検証しています。
- 今後、Fetcher / Evaluator / DatabaseManager 周辺テストを段階的に拡張予定です。

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
- 全タイムスタンプは JST (UTC+9) で統一されています

## 🛠️ 技術スタック

- **Language**: Python 3.10+
- **Frontend**: Streamlit (SVG Sparklines + HTML テーブル)
- **Database**: Supabase (PostgreSQL)
- **AI**: Google Gemini API
- **CI/CD**: GitHub Actions (15 分間隔 cron)
- **Deploy**: Streamlit Community Cloud
- **Timezone**: JST (UTC+9) 統一

## 📄 ライセンス

MIT License
