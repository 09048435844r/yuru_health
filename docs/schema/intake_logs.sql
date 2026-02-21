-- 摂取ログ（イベント駆動型、スナップショット保存）
-- Source of truth: 摂取記録時点の snapshot_payload を保持し、
-- config/supplements.yaml の後続変更の影響を受けない前提で運用する。
CREATE TABLE IF NOT EXISTS intake_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    scene TEXT NOT NULL,
    snapshot_payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_intake_logs_user_timestamp
    ON intake_logs (user_id, timestamp DESC);
