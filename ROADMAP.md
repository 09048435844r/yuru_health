# YuruHealth Roadmap

## 🏆 Philosophy
- **Input Minimal**: 手動入力は極限まで減らす。
- **Data Maximal**: Rawデータ（JSON）は全て保存する（Data Lake思想）。
- **Mobile First**: Galaxy Foldでの閲覧・操作を最優先。
- **Cloud Native**: どこからでもアクセス可能、かつサーバーレス。

---

## ✅ Phase 1: Foundation — Done
- Streamlit UI (Mobile Optimized)
- Withings API 連携 (OAuth2, 体重データ取得)
- Oura Ring API 連携 (睡眠・活動・コンディション)
- Environmental Logs (OpenWeatherMap + GPS)
- Gemini AI による健康データ評価

## ✅ Phase 2: Cloud Migration — Done
- Streamlit Community Cloud デプロイ
- Supabase (PostgreSQL) へのDB移行、SQLite廃止
- `secrets_loader` によるローカル/Cloud シークレット統一
- OAuth トークンの Supabase 永続化 (`oauth_tokens` テーブル)

## ✅ Phase 3: Samsung Health Integration — Done
- Google Cloud Project 設定、OAuth2 認証
- Google Fit Fetcher 実装 (歩数・睡眠・体重)
- Samsung Health → Health Connect → Google Fit → YuruHealth パイプライン

## 🎵 Phase 4: Context Awareness (Music & Life)
- **目的**: 音楽と健康データの相関分析。
- **Action**: Last.fm API連携、Listening Historyの取り込み。

## 🧠 Phase 5: Advanced AI Analysis
- **目的**: 蓄積されたRawデータ（JSON）のDeep Dive。
- **Action**: LangChain / Gemini Pro を用いた自然言語でのデータベースクエリ（Text-to-SQL）。

## 🎨 Phase 6: UI/UX Improvement
- **目的**: ダッシュボードの見やすさ・操作性向上。
- **Action**:
    - グラフのインタラクティブ化 (Plotly / Altair)
    - 週次・月次レポート自動生成
    - PWA対応の検討

## 📊 Phase 7: Data Analytics
- **目的**: 長期トレンド分析と健康インサイト。
- **Action**:
    - 体重・睡眠・活動の相関分析
    - 異常値検出アラート
    - 目標設定と進捗トラッキング
