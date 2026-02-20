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

## 6) 運用ポリシー（推奨）

### 推奨（A）

- OAuth同意画面を `In production` で運用
- 失効障害を最小化し、Input Minimal を守る

### 代替（B）

- `Testing` のまま運用
- 週1回の再認証を定期運用として明文化
- 障害時は本 Runbook で回復

---

## 7) 既知の実装上の保証

- OAuth失敗は fail-fast で検知（非ゼロ終了）
- Silent skip（例外握りつぶし）は排除済み

関連実装:

- `auth/exceptions.py`
- `auth/google_oauth.py`
- `src/fetchers/google_fit_fetcher.py`
- `src/main.py`

---

## 8) 参考コマンド

```bash
# バッチ実行
python -m src.main --auto

# Streamlit UI
streamlit run app.py
```
