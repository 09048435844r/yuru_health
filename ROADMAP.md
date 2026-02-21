# YuruHealth Roadmap

- 関連ドキュメント: [Docs Index](docs/README.md)

## 🏆 Philosophy
データをため込むことが第一優先、使い方は後で考えてもよい
- **Input Minimal**: 手動入力は極限まで減らす。
- **Data Maximal**: Rawデータ（JSON）は全て保存する（Data Lake思想）。
- **Mobile First**: Galaxy Foldでの閲覧・操作を最優先。
- **Cloud Native**: どこからでもアクセス可能、かつサーバーレス。
- **長期的な目標**: 健康管理の資産化を目指す。AIでの本人でも気がつかない傾向と対策をあぶり出す

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
- 単体テスト環境の構築 (`pytest`)
- CI/CD基礎（`pre-commit` hook による commit 前自動テスト）
- Google Fit OAuth 復旧・運用 Runbook 整備 (`docs/GOOGLE_FIT_OAUTH_RUNBOOK.md`)

## ✅ Phase 4: Reliability & Intake Logging — Done
- Fail-fast 運用を main/fetcher/auth まで貫通
  - OAuth トークン失効時に silent skip せず即時失敗（非ゼロ終了）
  - 例外握りつぶしを削減し、障害を検知可能な形で運用
- YAML ベース摂取ログ機能を実装
  - `config/supplements.yaml` を GitOps マスターとして運用
  - 記録時に `intake_logs.snapshot_payload` へ不変スナップショット保存
  - 後入力しやすい日時プリセット、誤記録取消（削除）導線を実装
- Deep Insight へ摂取成分日次サマリーを統合（raw_data と合わせて分析）

## 🚀 Phase 5: Discord自動通知（Next Priority）
- 目的: 異常や重要イベントを見逃さない運用を作る
- Action:
  - Deep Insight 結果や fetch 失敗を Discord Webhook へ通知
  - 日次サマリー（主要KPI + 摂取成分ハイライト）を定時配信
  - 通知のしきい値・送信時間・チャンネルを設定化

## 🎵 Phase 6: Context Awareness (Music & Life)
- **目的**: 音楽と健康データの相関分析。
- **Action**: Last.fm API連携、Listening Historyの取り込み。

## 🧠 Phase 7: Advanced AI Analysis
- **目的**: 蓄積されたRawデータ（JSON）のDeep Dive。
- **Action**: LangChain / Gemini Pro を用いた自然言語でのデータベースクエリ（Text-to-SQL）。

## 🎨 Phase 8: UI/UX Improvement
- **目的**: ダッシュボードの見やすさ・操作性向上。
- **Action**:
    - グラフのインタラクティブ化 (Plotly / Altair)
    - 週次・月次レポート自動生成
    - PWA対応の検討

## 📊 Phase 9: Data Analytics
- **目的**: 長期トレンド分析と健康インサイト。
- **Action**:
    - 体重・睡眠・活動の相関分析
    - 異常値検出アラート
    - 目標設定と進捗トラッキング

## 🖥️ Future Vision: Self-hosting on Synology NAS
- **目的**: ローカルネットワーク中心の爆速レスポンスと運用コスト最適化。
- **Milestones**:
  - Streamlit + Python batch を Docker 化し NAS 上で常駐
  - Supabase 連携継続 or Postgres ローカル併用の比較検証
  - バックアップ／復旧／ゼロダウンタイム更新手順を標準化
