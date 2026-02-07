# YuruHealth v3.1 Roadmap

## 🏆 Philosophy
- **Input Minimal**: 手動入力は極限まで減らす。
- **Data Maximal**: Rawデータ（JSON）は全て保存する（Data Lake思想）。
- **Mobile First**: Galaxy Foldでの閲覧・操作を最優先。
- **Cloud Native**: どこからでもアクセス可能、かつサーバーレス。

## ✅ Phase 1: Foundation (完了)
- Streamlit UI (Mobile Optimized)
- Withings / Oura Ring API 連携
- Environmental Logs (OpenWeatherMap + GPS)

## � Phase 2: Cloud Migration (Current Focus)
- **目的**: ローカル環境（WSL2）からの脱却とスマホアクセス。
- **Infrastructure**:
    - App: Streamlit Community Cloud (GitHub連携)
    - DB: Supabase (PostgreSQL)
- **Action**: SQLite廃止、Supabaseクライアント実装、デプロイ。

## 🩺 Phase 3: Samsung Health Integration
- **目的**: Galaxy Watch / Samsung Health の詳細データ取り込み。
- **Strategy**: Samsung Health -> Health Connect -> Google Fit -> **Google Cloud API** -> YuruHealth.
- **Action**: Google Cloud Project設定、Google Fit Fetcher実装。

## 🎵 Phase 4: Context Awareness (Music & Life)
- **目的**: 音楽と健康データの相関分析。
- **Action**: Last.fm API連携、Listening Historyの取り込み。

## � Phase 5: Advanced AI Analysis
- **目的**: 蓄積されたRawデータ（JSON）のDeep Dive。
- **Action**: LangChain / Gemini Pro を用いた自然言語でのデータベースクエリ（Text-to-SQL）。
