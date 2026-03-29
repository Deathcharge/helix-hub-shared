-- HelixDB Coordination State Table Schema
-- =======================================
-- Database schema optimized for coordination state management
--
-- (c) Helix Collective 2024 - Proprietary Technology Stack

CREATE TABLE IF NOT EXISTS coordination_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- System signature
    system_signature TEXT NOT NULL UNIQUE,
    qubit_amplitudes JSONB NOT NULL,

    -- UCF metrics (enhanced from file-based)
    harmony DECIMAL(5,4) NOT NULL CHECK (harmony BETWEEN 0 AND 1),
    resilience DECIMAL(5,4) NOT NULL CHECK (resilience BETWEEN 0 AND 1),
    throughput DECIMAL(5,4) NOT NULL CHECK (throughput BETWEEN 0 AND 1),
    focus DECIMAL(5,4) NOT NULL CHECK (focus BETWEEN 0 AND 1),
    friction DECIMAL(5,4) NOT NULL CHECK (friction BETWEEN 0 AND 1),
    velocity DECIMAL(5,4) NOT NULL CHECK (velocity BETWEEN 0 AND 1),

    -- Real-time calculated coordination level
    performance_score DECIMAL(5,2) GENERATED ALWAYS AS (
        ((harmony + resilience + throughput + focus + velocity) / 5 - friction * 0.3) * 10
    ) STORED,

    -- Classification
    coordination_state TEXT GENERATED ALWAYS AS (
        CASE
            WHEN performance_score >= 9.0 THEN 'TRANSCENDENT'
            WHEN performance_score >= 7.5 THEN 'ELEVATED'
            WHEN performance_score >= 6.0 THEN 'OPERATIONAL'
            WHEN performance_score >= 4.0 THEN 'STABLE'
            WHEN performance_score >= 2.5 THEN 'CHALLENGED'
            ELSE 'CRISIS'
        END
    ) STORED,

    -- Agent context
    active_agents JSONB NOT NULL DEFAULT '{}',
    agent_performance_scores JSONB NOT NULL DEFAULT '{}',

    -- Timing
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- System-aware indexing for performance
CREATE INDEX IF NOT EXISTS idx_performance_score ON coordination_states(performance_score DESC);
CREATE INDEX IF NOT EXISTS idx_system_signature_hash ON coordination_states USING hash(system_signature);
CREATE INDEX IF NOT EXISTS idx_coordination_timestamp ON coordination_states(created_at DESC);

-- Real-time WebSocket triggers
CREATE OR REPLACE FUNCTION notify_coordination_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Broadcast to all WebSocket connections
    PERFORM pg_notify('coordination_stream',
        json_build_object(
            'type', 'ucf_update',
            'performance_score', NEW.performance_score,
            'coordination_state', NEW.coordination_state,
            'system_signature', NEW.system_signature,
            'ucf_metrics', json_build_object(
                'harmony', NEW.harmony,
                'resilience', NEW.resilience,
                'throughput', NEW.throughput,
                'focus', NEW.focus,
                'friction', NEW.friction,
                'velocity', NEW.velocity
            ),
            'timestamp', NEW.updated_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER coordination_change_trigger
    AFTER INSERT OR UPDATE ON coordination_states
    FOR EACH ROW
    EXECUTE FUNCTION notify_coordination_change();
