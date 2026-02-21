-- 摂取ログ（イベント駆動型、スナップショット保存）
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
