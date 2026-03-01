# Google Fit OAuth 復旧・運用 Runbook

このドキュメントは、Google Fit 連携で `invalid_grant`（トークン失効/無効）になった際の復旧手順と、恒久運用方針をまとめたものです。

---

## 🎯 目的

- Google OAuth 再認証で `oauth_tokens` を更新する
- `python -m src.main --auto` が再び `exit code 0` で通る状態に戻す
- `google_fit_data` の欠損期間を回復する
- 7日失効（Testing モード）を避ける恒久運用を決める

---

## 1) 障害シグナル（検知条件）

以下が出たら本 Runbook を実行します。

- バッチ実行で失敗
  - `python -m src.main --auto` が `exit code 1`
- ログで以下のいずれか
  - `invalid_grant: Token has been expired or revoked.`
  - `Google OAuth failed`
  - `Google Fit 歩数取得エラー`

---

## 2) 事前確認（Read-Only）

```bash
python - <<'PY'
from src.database_manager import DatabaseManager
DB=DatabaseManager('config/secrets.yaml')
meta = DB.supabase.table('oauth_tokens').select('user_id,provider,updated_at').eq('user_id','user_001').eq('provider','google').limit(1).execute().data
latest = DB.supabase.table('google_fit_data').select('date').order('date', desc=True).limit(1).execute().data
count = DB.supabase.table('google_fit_data').select('id', count='exact').limit(1).execute().count
print('oauth_meta=', meta)
print('google_fit_latest=', latest[0]['date'] if latest else None)
print('google_fit_count=', count)
PY
```

---

## 3) 復旧手順（再認証）

### Step A: GCP OAuth 同意画面の公開ステータス確認（推奨）

1. GCP Console → APIs & Services → OAuth consent screen
2. Publishing status が `Testing` の場合は `Publish app` を実行

> 個人利用でも In production 化しておくと、7日失効リスクを大幅に下げられます。

### Step B: Streamlit から Google 再認証

```bash
streamlit run app.py
```

UI 操作:

1. 「🏃 Google Fit データ」セクションを開く
2. すでに認証済み表示でも一度「🚪 Google Fit ログアウト」を押す
3. 「🔗 Google Fit にログイン」を押し、Google 同意画面で承認
4. 戻ってきたら「📥 Google Fit データ取得」を実行

---

## 4) リカバリ実行

```bash
python -m src.main --auto
```

期待値:

- 終了コードが `0`
- サマリーログで `GoogleFit:<正の件数>`

---

## 5) 復旧後検証（Read-Only）

```bash
python - <<'PY'
import json
from src.database_manager import DatabaseManager
DB=DatabaseManager('config/secrets.yaml')

meta = DB.supabase.table('oauth_tokens').select('user_id,provider,updated_at').eq('user_id','user_001').eq('provider','google').limit(1).execute().data
latest = DB.supabase.table('google_fit_data').select('date').order('date', desc=True).limit(1).execute().data
count = DB.supabase.table('google_fit_data').select('id', count='exact').limit(1).execute().count
rows = DB.supabase.table('google_fit_data').select('date,data_type').gte('date','2026-02-18').order('date').limit(5000).execute().data

per = {}
for r in rows:
    per.setdefault(r['date'], 0)
    per[r['date']] += 1

print(json.dumps({
  'oauth_google_meta': meta,
  'google_fit_latest': latest[0]['date'] if latest else None,
  'google_fit_count': count,
  'google_fit_rows_from_2026_02_18': len(rows),
  'google_fit_per_day_since_2026_02_18': per,
}, ensure_ascii=False, indent=2))
PY
```

判定基準:

- `oauth_tokens.updated_at` が再認証時刻に更新されている
- `google_fit_data.latest` が当日まで進んでいる
- `google_fit_data.count` が増えている

---

## 6) 睡眠データ異常値（過大計上）復旧手順

Google Fit の睡眠が `16〜22時間` のように過大計上される場合は、
`raw_data_lake` から再パースして `google_fit_data` を正規化します。

```bash
python -m src.main --parse-only --days 7
```

実装上の正規化ルール:

- セッション重複は日次(JST)で interval union
- `awake_keywords` に一致する区間は差し引き
- 複数アプリ由来の重複は `source_policy` で 1 ソース採用

### 正規化結果の確認（Read-Only）

```bash
python - <<'PY'
from src.database_manager import DatabaseManager
DB=DatabaseManager('config/secrets.yaml')
rows=(DB.supabase.table('google_fit_data')
      .select('date,value,raw_data')
      .eq('user_id','user_001')
      .eq('data_type','sleep')
      .order('date', desc=True)
      .limit(7)
      .execute().data or [])
for r in rows:
    raw = r.get('raw_data') if isinstance(r.get('raw_data'), dict) else {}
    print(r.get('date'), r.get('value'), raw.get('chosen_app'), raw.get('source_policy'))
PY
```

判定基準:

- `value` が常識的な範囲（例: 240〜600分）に収まる
- `raw_data.chosen_app` が保存されている
- `raw_data.source_policy` が設定値と一致する

---

## 7) sleep_parser 設定（config/settings.yaml）

`config/settings.yaml` で睡眠ソース選定ポリシーを調整できます。

```yaml
google_fit:
  sleep_parser:
    source_policy: "min" # min / max / oura / shealth / healthsync / prefer:<packageName>
    min_candidate_minutes: 120
    awake_keywords: ["awake", "wake", "覚醒"]
```

- `min`: 候補のうち最小値を採用（過大計上を抑制）
- `max`: 候補のうち最大値を採用
- `oura` など: 特定アプリを優先
- `prefer:<packageName>`: パッケージ名を直接指定

---

## 8) 運用ポリシー（推奨）

### 推奨（A）

- OAuth同意画面を `In production` で運用
- 失効障害を最小化し、Input Minimal を守る

### 代替（B）

- `Testing` のまま運用
- 週1回の再認証を定期運用として明文化
- 障害時は本 Runbook で回復

---

## 9) 既知の実装上の保証

- OAuth失敗は fail-fast で検知（非ゼロ終了）
- Silent skip（例外握りつぶし）は排除済み
- 睡眠再パースは Union + Awake除外 + source_policy 適用

関連実装:

- `auth/exceptions.py`
- `auth/google_oauth.py`
- `src/fetchers/google_fit_fetcher.py`
- `src/main.py`
- `config/settings.yaml`
- `app.py`

---

## 10) 参考コマンド

```bash
# バッチ実行
python -m src.main --auto

# parser-only 再集計
python -m src.main --parse-only --days 7

# Streamlit UI
streamlit run app.py
```
