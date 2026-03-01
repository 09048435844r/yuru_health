# google_fit_data スキーマ補足

`google_fit_data` テーブルのうち、**sleep レコード (`data_type='sleep'`) の `raw_data`** に保存される
メタ情報を説明します。

## raw_data フィールド（sleep）

- `day` (string)
  - 集計対象日（JST, `YYYY-MM-DD`）
- `sleep_minutes_sum` (number)
  - 正規化後の睡眠分
- `chosen_app` (string | null)
  - 当日の採用ソース（例: `com.ouraring.oura`）
- `candidate_minutes` (object)
  - 候補ソースごとの睡眠分
  - 例: `{ "com.ouraring.oura": 423, "com.sec.android.app.shealth": 392 }`
- `source_policy` (string | null)
  - ソース選定ポリシー
  - 例: `min`, `max`, `oura`, `shealth`, `healthsync`, `prefer:<packageName>`

## 生成ルール（概要）

`python -m src.main --parse-only --days N` 実行時、Google Fit 睡眠は以下で再計算されます。

1. セッションを JST 日次へ分割
2. セッション区間を union（重複時間の二重加算防止）
3. `awake_keywords` 一致区間を差し引き
4. `source_policy` で当日1ソースを選定し `chosen_app` に保存

詳細運用は以下を参照:

- `docs/GOOGLE_FIT_OAUTH_RUNBOOK.md`
- `docs/API_INTEGRATION.md`
