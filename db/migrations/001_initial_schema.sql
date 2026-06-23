-- FitAi — Initial Schema Migration
-- WAL mode for concurrent reads from bot + Prefect processes
PRAGMA journal_mode=WAL;

-- Daily Fitbit data: persisted by morning_report_flow each day
CREATE TABLE daily_health_logs (
    date                TEXT PRIMARY KEY,   -- ISO date: '2026-05-30'
    steps               INTEGER,
    steps_goal          INTEGER NOT NULL DEFAULT 10000,
    sleep_duration_hrs  REAL,
    sleep_quality       TEXT,               -- 'poor' (<6hrs) / 'fair' (6-7hrs) / 'good' (>=7hrs)
    fetched_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Meal logs: multiple entries per meal type per day supported
CREATE TABLE meal_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    date             TEXT NOT NULL,         -- ISO date
    meal_type        TEXT NOT NULL,         -- breakfast/lunch/dinner/snack
    logged_at        TEXT NOT NULL,
    foods_identified TEXT,                  -- JSON array
    macros           TEXT,                  -- JSON object
    flags            TEXT,                  -- JSON object
    score            INTEGER
);

-- Static user profile: single row, manually set during onboarding, updated via /profile update
CREATE TABLE user_profile (
    id                  INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    name                TEXT,
    age                 INTEGER,
    gender              TEXT,
    height_cm           REAL,
    weight_kg           REAL,
    diet_type           TEXT,        -- 'omnivore' | 'vegetarian' | 'vegan'
    allergies           TEXT,        -- JSON array: ['peanuts', 'shellfish']
    intolerances        TEXT,        -- JSON array: ['lactose', 'gluten']
    avoided_foods       TEXT,        -- JSON array: ['alcohol', 'beef']
    preferred_cuisines  TEXT,        -- JSON array: ['indian', 'mediterranean']
    activity_level      TEXT,        -- 'sedentary' | 'moderate' | 'active'
    calorie_target      INTEGER,
    protein_target_g    INTEGER,
    carb_target_g       INTEGER,
    fat_target_g        INTEGER,
    fiber_target_g      INTEGER,
    step_goal           INTEGER DEFAULT 10000,
    sleep_goal_hrs      REAL    DEFAULT 7.0,
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Health profile: one row per lab report upload — accumulates over time as new reports arrive
-- Agents query most recent row (ORDER BY report_date DESC LIMIT 1)
-- History preserved for trend analysis (WeeklyReportAgent, HealthInsightsAgent)
CREATE TABLE user_health_profile (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date     TEXT NOT NULL UNIQUE,   -- ISO date: '2026-05-30' — enforces one row per visit
    a1c             REAL,
    a1c_target      REAL,
    ldl             INTEGER,
    ldl_target      INTEGER,
    hdl             INTEGER,
    triglycerides   INTEGER,
    medications     TEXT,                   -- JSON array
    bmi             REAL,
    uploaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Personalised nutrition rules: append-with-status, rules are never deleted
-- Active rules: WHERE is_active = 1
-- When a lab update makes a rule obsolete: set is_active=0, remark='why', deactivated_at=now
-- When a previously deactivated rule becomes relevant again: set is_active=1, remark=NULL, deactivated_at=NULL
CREATE TABLE user_nutrition_guidance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule            TEXT NOT NULL,           -- "Limit carbs to 45g/meal given A1C 6.4%"
    category        TEXT NOT NULL,           -- 'a1c' | 'ldl' | 'hdl' | 'weight' | 'general'
    source          TEXT,                    -- 'health_profile' | 'knowledge_base'
    priority        INTEGER DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1,
    remark          TEXT,                    -- why deactivated (NULL when active)
    source_lab_date TEXT,                    -- report_date of the lab that created this rule
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    deactivated_at  TEXT
);

-- Daily summaries
CREATE TABLE daily_summaries (
    date            TEXT PRIMARY KEY,       -- ISO date
    total_macros    TEXT,                   -- JSON object
    dietary_score   INTEGER,
    improvements    TEXT,                   -- JSON array: [{category, recommendation, foods_to_watch}]
    sent_at         TEXT
);

-- Weekly reports
CREATE TABLE weekly_reports (
    week_start          TEXT PRIMARY KEY,   -- ISO date (Monday)
    avg_dietary_score   INTEGER,
    score_delta         INTEGER,
    patterns_detected   TEXT,               -- JSON array
    recommendations     TEXT,               -- JSON object (for follow-through comparison)
    skip_comparison     INTEGER DEFAULT 0,  -- 0/1 boolean
    sent_at             TEXT
);

-- Pattern callouts (for escalation tracking)
CREATE TABLE patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,          -- ISO date
    pattern_type    TEXT NOT NULL,
    streak_days     INTEGER NOT NULL,
    sent_at         TEXT
);

-- Semantic memory: extracted behavioural facts, refreshed weekly
CREATE TABLE user_semantic_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,  -- 'meal_pattern' | 'sleep_pattern' | 'activity_pattern' | 'behavioral'
    fact        TEXT NOT NULL,  -- human-readable extracted fact
    confidence  TEXT NOT NULL,  -- 'strong' | 'moderate' | 'weak'
    evidence    TEXT,           -- JSON: data points that support this fact
    valid_from  TEXT NOT NULL,  -- ISO date: earliest data this is drawn from
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indian foods lookup table (IFCT/NIN data)
CREATE TABLE indian_foods (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,   -- e.g. "dal makhani", "tawa roti"
    calories_per_100g   REAL,
    protein_g           REAL,
    carbs_g             REAL,
    fat_g               REAL,
    fiber_g             REAL,
    saturated_fat_g     REAL,
    sugar_g             REAL,
    glycemic_index      INTEGER,
    notes               TEXT                -- e.g. "varies with ghee quantity"
);

-- Indexes for frequently-queried columns
CREATE INDEX idx_meal_logs_date ON meal_logs(date);
CREATE INDEX idx_patterns_date_type ON patterns(date, pattern_type);
