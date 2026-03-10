# Operations Playbook

YuruHealth データパイプラインの日次運用・障害対応手順です。

---

## 1. 日次ヘルスチェック

### 1-1. バッチ実行確認

- GitHub Actions `periodic_fetch.yml` の最新実行を確認
- 失敗時はログの `fetch done | ...` と `error` 行を確認

ローカル worker（Raspberry Pi）運用時は、取得周期も確認します。

```bash
docker compose exec worker printenv FETCH_INTERVAL_SECONDS
docker compose logs worker --since=30m | grep -E "start fetch|done rc|fetch done"
```

期待値:

- `FETCH_INTERVAL_SECONDS=900`（15分）
- `start fetch` が概ね15分周期（再起動直後の過渡は除く）

### 1-2. DB鮮度確認（Read-Only）

```bash
python - <<'PY'
from src.database_manager import DatabaseManager
DB=DatabaseManager('config/secrets.yaml')

def latest(table,col):
    d=DB.supabase.table(table).select(col).order(col,desc=True).limit(1).execute().data
    return d[0][col] if d else None

print('weight_data.latest=', latest('weight_data','measured_at'))
print('oura_data.latest=', latest('oura_data','measured_at'))
print('google_fit_data.latest=', latest('google_fit_data','date'))
print('environmental_logs.latest=', latest('environmental_logs','timestamp'))
PY
```

### 1-3. Raspberry Pi システム監視（SQLite）

システム監視は Supabase と分離され、`data/system_health.db` に保存されます。

確認手順:

```bash
docker compose ps system_health_worker
docker compose logs --tail=50 system_health_worker

python - <<'PY'
import sqlite3
conn = sqlite3.connect('data/system_health.db')
row = conn.execute(
    "SELECT measured_at, cpu_temp_c, cpu_percent, memory_percent, disk_percent "
    "FROM system_health_logs ORDER BY measured_at DESC LIMIT 1"
).fetchone()
print('latest_system_health=', row)
count = conn.execute("SELECT COUNT(*) FROM system_health_logs").fetchone()[0]
print('rows=', count)
conn.close()
PY
```

期待値:

- 約5分ごとに最新行が更新される
- 30日を超える古いデータは自動削除される

---

## 2. ローカル再現（最短）

```bash
python -m src.main --auto
```

判定:
- `exit code 0`: 正常
- `exit code 1`: fail-fast により異常検知（要原因調査）

補足（Google Fit 睡眠の再集計）:

```bash
python -m src.main --parse-only --days 7
```

- 外部API取得は行わず、`raw_data_lake` から parsed テーブルを再構築
- Google Fit 睡眠は Union + Awake除外 + source_policy で再計算

補足（SwitchBot / Weather の再構築）:

- parse-only は環境ログ再構築時に `fetched_at` 優先で timestamp 化する
- 同日内の複数データ点が保持され、足跡スパークラインの点数不足を回避しやすい

---

## 3. 障害種別ごとの切り分け

### A. 認証系（OAuth）

シグナル:
- `invalid_grant`
- `OAuth failed`
- `token refresh failed`

対応:
1. 該当 provider の `oauth_tokens` 更新日時を確認
2. 再認証を実施
3. バッチ再実行

Google Fit の詳細は:
- [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md)

### B. シークレット/設定系

シグナル:
- `StreamlitSecretNotFoundError`
- `Invalid API key`
- Supabase 接続エラー

対応:
1. 設定ロード優先順位を確認
2. URL/KEY の整形結果を確認
3. `python -m src.main --auto` で再試行

設定詳細は:
- [Secrets & Config Guide](./SECRETS_CONFIGURATION.md)

### C. データ重複・未挿入

シグナル:
- `Skipped duplicate ...` が大量に出る

解釈:
- これはハッシュ/一意判定による正常スキップの可能性がある
- 認証失敗による 0件 とは区別する

確認:
- latest が進んでいるか
- 件数が必要範囲で増えているか

Google Fit 睡眠の追加確認:

- `google_fit_data.data_type='sleep'` の `raw_data.chosen_app` が入っているか
- 値が常識範囲（目安: 240〜600分）か

SwitchBot 足跡の追加確認:

- 足跡最下段（SwitchBot）は **CO2(ppm)** スパークライン表示
- `environmental_logs.source='switchbot'` の当日 CO2 データ点が 2 点以上あるか

### D. Raspberry Pi 監視データが更新されない

シグナル:

- `system_health_worker` が停止している
- UI の「サーバー・ヘルス」タブにデータが出ない

対応:

1. `docker compose ps system_health_worker` で状態確認
2. `docker compose logs --tail=100 system_health_worker` で例外確認
3. `/sys` `/proc` の read-only マウント確認（`docker-compose.yml`）
4. `data/system_health.db` の最新 `measured_at` が進んでいるか確認

---

## 4. インシデント時の報告テンプレート

- 発生時刻 (JST):
- 影響範囲（source/table）:
- 事実（ログ/件数/最新日時）:
- 仮説:
- 実施対応:
- 現在状態（復旧/未復旧）:
- 次アクション:

---

## 5. 設計上の前提（現在）

- OAuth障害は fail-fast（非ゼロ終了）
- Silent skip（例外握りつぶし）は削除済み
- 重複スキップは正常挙動としてログ出力される
