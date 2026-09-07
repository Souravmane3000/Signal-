-- Signal Phase 2 Supabase Schema
-- Canonical source of truth. Applied by scripts/migrate_supabase.py.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- user_configs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_configs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users NOT NULL,
    keywords text[],
    verticals text[],
    stage_filter text[],
    schedule_freq text,
    delivery_email text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_configs_user_id ON user_configs (user_id);

ALTER TABLE user_configs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_configs_user_scope ON user_configs;
CREATE POLICY user_configs_user_scope ON user_configs
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- briefing_runs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS briefing_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users NOT NULL,
    run_at timestamptz DEFAULT now(),
    status text,
    raw_findings jsonb,
    final_briefing text,
    was_approved boolean DEFAULT false,
    approved_at timestamptz,
    thread_id text,
    run_config jsonb
);

ALTER TABLE briefing_runs ADD COLUMN IF NOT EXISTS graph_version text;
ALTER TABLE briefing_runs ADD COLUMN IF NOT EXISTS thread_id text;
ALTER TABLE briefing_runs ADD COLUMN IF NOT EXISTS run_config jsonb;

CREATE INDEX IF NOT EXISTS idx_briefing_runs_user_id ON briefing_runs (user_id);
CREATE INDEX IF NOT EXISTS idx_briefing_runs_thread_id ON briefing_runs (thread_id);
CREATE INDEX IF NOT EXISTS idx_briefing_runs_user_id_run_at ON briefing_runs (user_id, run_at DESC);

ALTER TABLE briefing_runs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS briefing_runs_user_scope ON briefing_runs;
CREATE POLICY briefing_runs_user_scope ON briefing_runs
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- briefing_items
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS briefing_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_run_id uuid REFERENCES briefing_runs NOT NULL,
    user_id uuid REFERENCES auth.users NOT NULL,
    title text,
    summary text,
    source_url text,
    source_name text,
    category text,
    confidence_score float,
    entities jsonb,
    embedding vector(1536),
    feedback text,
    feedback_reason text,
    feedback_at timestamptz
);

ALTER TABLE briefing_items ADD COLUMN IF NOT EXISTS embedding vector(1536);

CREATE INDEX IF NOT EXISTS idx_briefing_items_briefing_run_id ON briefing_items (briefing_run_id);
CREATE INDEX IF NOT EXISTS idx_briefing_items_user_id ON briefing_items (user_id);

ALTER TABLE briefing_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS briefing_items_user_scope ON briefing_items;
CREATE POLICY briefing_items_user_scope ON briefing_items
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name_raw text NOT NULL,
    name_normalized text NOT NULL,
    sector text,
    stage text,
    location text,
    founded_year int,
    yc_batch text,
    greenhouse_slug text,
    lever_slug text,
    first_seen_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_companies_name_normalized ON companies (name_normalized);

ALTER TABLE companies ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS companies_authenticated_read ON companies;
CREATE POLICY companies_authenticated_read ON companies
    FOR SELECT
    TO authenticated
    USING (true);

DROP POLICY IF EXISTS companies_authenticated_write ON companies;
CREATE POLICY companies_authenticated_write ON companies
    FOR INSERT
    TO authenticated
    WITH CHECK (true);

DROP POLICY IF EXISTS companies_authenticated_update ON companies;
CREATE POLICY companies_authenticated_update ON companies
    FOR UPDATE
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- funding_rounds
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS funding_rounds (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid REFERENCES companies,
    amount_usd bigint,
    stage text,
    announced_at date,
    source_url text,
    investor_names text[],
    investor_names_normalized text[],
    briefing_item_id uuid REFERENCES briefing_items,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_funding_rounds_company_id ON funding_rounds (company_id);
CREATE INDEX IF NOT EXISTS idx_funding_rounds_briefing_item_id ON funding_rounds (briefing_item_id);

ALTER TABLE funding_rounds ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS funding_rounds_user_scope ON funding_rounds;
CREATE POLICY funding_rounds_user_scope ON funding_rounds
    FOR ALL
    USING (
        EXISTS (
            SELECT 1
            FROM briefing_items bi
            WHERE bi.id = funding_rounds.briefing_item_id
              AND bi.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM briefing_items bi
            WHERE bi.id = funding_rounds.briefing_item_id
              AND bi.user_id = auth.uid()
        )
    );

-- ---------------------------------------------------------------------------
-- agent_run_metrics
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_run_metrics (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    briefing_run_id uuid REFERENCES briefing_runs NOT NULL,
    user_id uuid REFERENCES auth.users NOT NULL,
    run_at timestamptz DEFAULT now(),
    sources_queried text[],
    findings_retrieved int,
    findings_dropped_freshness int,
    findings_dropped_scope int,
    findings_dropped_dedup int,
    findings_in_briefing int,
    tokens_used int,
    estimated_cost_usd float,
    run_duration_seconds float,
    tavily_result_count int,
    yc_result_count int,
    hn_result_count int,
    rss_result_count int
);

ALTER TABLE agent_run_metrics ADD COLUMN IF NOT EXISTS graph_version text;
ALTER TABLE agent_run_metrics ADD COLUMN IF NOT EXISTS source_health jsonb;

CREATE INDEX IF NOT EXISTS idx_agent_run_metrics_briefing_run_id ON agent_run_metrics (briefing_run_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_metrics_user_id ON agent_run_metrics (user_id);
CREATE INDEX IF NOT EXISTS idx_agent_run_metrics_user_id_run_at ON agent_run_metrics (user_id, run_at DESC);

ALTER TABLE agent_run_metrics ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_run_metrics_user_scope ON agent_run_metrics;
CREATE POLICY agent_run_metrics_user_scope ON agent_run_metrics
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- user_feedback
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users NOT NULL,
    briefing_item_id uuid REFERENCES briefing_items,
    category text,
    source_name text,
    feedback text,
    reason text,
    created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback (user_id);
CREATE INDEX IF NOT EXISTS idx_user_feedback_briefing_item_id ON user_feedback (briefing_item_id);

ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_feedback_user_scope ON user_feedback;
CREATE POLICY user_feedback_user_scope ON user_feedback
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- agent_memory
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_memory (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES auth.users NOT NULL,
    memory_type text,
    namespace_key text,
    content jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_user_id ON agent_memory (user_id);
CREATE INDEX IF NOT EXISTS idx_agent_memory_type ON agent_memory (user_id, memory_type);

ALTER TABLE agent_memory ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_memory_user_scope ON agent_memory;
CREATE POLICY agent_memory_user_scope ON agent_memory
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
