# Operations Playbook

YuruHealth データパイプラインの日次運用・障害対応手順です。

---

## 1. 日次ヘルスチェック

### 1-1. バッチ実行確認

- GitHub Actions `periodic_fetch.yml` の最新実行を確認
- 失敗時はログの `fetch done | ...` と `error` 行を確認

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

---

## 2. ローカル再現（最短）

```bash
python -m src.main --auto
```

判定:
- `exit code 0`: 正常
- `exit code 1`: fail-fast により異常検知（要原因調査）

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
