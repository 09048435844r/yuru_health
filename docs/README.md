# Docs Index

YuruHealth の運用・連携ドキュメント一覧です。

## 主要ドキュメント

- [Roadmap](../ROADMAP.md)
  - プロダクトの中長期計画と現在の優先度
- [API連携ガイド](./API_INTEGRATION.md)
  - Withings / Oura 設定、Google Fit 睡眠異常時の parser-only 再集計手順
- [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md)
  - `invalid_grant` 復旧、再認証、欠損回復、睡眠正規化（Union/Awake除外/source_policy）
- [Operations Playbook](./OPERATIONS_PLAYBOOK.md)
  - 日次運用、障害時の切り分け、確認コマンド
- [Intake Logging 運用マニュアル](./operations_intake_logging.md)
  - 摂取ログのGitOps運用、YAML変更手順、プリセット/成分更新（1単位あたり + `default_quantity` モデル）
- [Secrets & Config Guide](./SECRETS_CONFIGURATION.md)
  - `secrets_loader` 優先順位、ローカル/CI/Cloud の設定指針
- [Schema: google_fit_data 補足](./schema/google_fit_data.md)
  - `data_type='sleep'` の `raw_data`（chosen_app/source_policy/candidate_minutes）の意味

## 推奨の読み順

1. 新規セットアップ: `README.md` → `SECRETS_CONFIGURATION.md`
2. API連携: `API_INTEGRATION.md`
3. 摂取ログ運用: `operations_intake_logging.md`
4. 障害対応: `OPERATIONS_PLAYBOOK.md` → 必要に応じて `GOOGLE_FIT_OAUTH_RUNBOOK.md`
