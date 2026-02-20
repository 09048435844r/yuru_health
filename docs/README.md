# Docs Index

YuruHealth の運用・連携ドキュメント一覧です。

## 主要ドキュメント

- [Roadmap](../ROADMAP.md)
  - プロダクトの中長期計画と現在の優先度
- [API連携ガイド](./API_INTEGRATION.md)
  - Withings / Oura の設定と基本トラブルシュート
- [Google Fit OAuth 復旧・運用 Runbook](./GOOGLE_FIT_OAUTH_RUNBOOK.md)
  - `invalid_grant` 復旧、再認証、欠損回復
- [Operations Playbook](./OPERATIONS_PLAYBOOK.md)
  - 日次運用、障害時の切り分け、確認コマンド
- [Secrets & Config Guide](./SECRETS_CONFIGURATION.md)
  - `secrets_loader` 優先順位、ローカル/CI/Cloud の設定指針

## 推奨の読み順

1. 新規セットアップ: `README.md` → `SECRETS_CONFIGURATION.md`
2. API連携: `API_INTEGRATION.md`
3. 障害対応: `OPERATIONS_PLAYBOOK.md` → 必要に応じて `GOOGLE_FIT_OAUTH_RUNBOOK.md`
