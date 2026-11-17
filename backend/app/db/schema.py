from __future__ import annotations

import sqlite3

MIGRATE_SQL: list[tuple[str, str]] = [
    (
        "001_init",
        """
CREATE TABLE IF NOT EXISTS schema_migrations (
  id TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  description TEXT,
  style TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  progress INTEGER NOT NULL DEFAULT 0,
  episode_count INTEGER NOT NULL DEFAULT 1,
  current_step INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  number INTEGER NOT NULL DEFAULT 1,
  name TEXT,
  location TEXT,
  time TEXT,
  characters_json TEXT NOT NULL DEFAULT '[]',
  props_json TEXT NOT NULL DEFAULT '[]',
  description TEXT,
  description_en TEXT,
  prompt_cn TEXT,
  prompt_en TEXT,
  negative_prompt TEXT,
  interpretation_cn TEXT,
  dialogue_count INTEGER NOT NULL DEFAULT 0,
  narration_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  name TEXT,
  name_en TEXT,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  prompt_cn TEXT,
  prompt_en TEXT,
  negative_prompt TEXT,
  model TEXT,
  image_url TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS storyboard_frames (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  number INTEGER NOT NULL DEFAULT 1,
  description TEXT,
  description_en TEXT,
  character TEXT,
  scene TEXT,
  shot_type TEXT,
  angle TEXT,
  movement TEXT,
  duration REAL,
  prompt_cn TEXT,
  prompt_en TEXT,
  negative_prompt TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  image_url TEXT,
  asset_id TEXT,
  model TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id);
CREATE INDEX IF NOT EXISTS idx_frames_project ON storyboard_frames(project_id);
""",
    ),
    (
        "002_jobs",
        """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  project_id TEXT,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  result_json TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  link_path TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id);
""",
    ),
    (
        "003_rag_cases",
        """
CREATE TABLE IF NOT EXISTS rag_cases (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT NOT NULL,
  style TEXT,
  description TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  prompt_en TEXT,
  negative_prompt TEXT,
  source_project_id TEXT,
  source_ref TEXT,
  rating REAL NOT NULL DEFAULT 0,
  usage_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_cases_type ON rag_cases(type);
""",
    ),
    (
        "004_render_tts",
        """
ALTER TABLE scenes ADD COLUMN lines_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE storyboard_frames ADD COLUMN lines_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE storyboard_frames ADD COLUMN scene_id TEXT;
CREATE TABLE IF NOT EXISTS renders (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  scene_id TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  engine TEXT NOT NULL DEFAULT 'edge',
  output_url TEXT,
  duration_sec REAL,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_renders_project ON renders(project_id);
""",
    ),
    (
        "005_frame_video",
        """
ALTER TABLE storyboard_frames ADD COLUMN video_url TEXT;
ALTER TABLE storyboard_frames ADD COLUMN video_status TEXT;
ALTER TABLE storyboard_frames ADD COLUMN video_error TEXT;
ALTER TABLE storyboard_frames ADD COLUMN video_job_id TEXT;
""",
    ),
    (
        "006_prompt_locks",
        """
ALTER TABLE assets ADD COLUMN lock_en TEXT NOT NULL DEFAULT '';
ALTER TABLE storyboard_frames ADD COLUMN motion_prompt_en TEXT NOT NULL DEFAULT '';
""",
    ),
    (
        "007_asset_aspect",
        """
ALTER TABLE assets ADD COLUMN aspect TEXT NOT NULL DEFAULT 'square';
""",
    ),
    (
        "008_prompt_templates",
        """
CREATE TABLE IF NOT EXISTS prompt_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL DEFAULT '',
  name_en TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT '',
  category_name TEXT NOT NULL DEFAULT '',
  version TEXT NOT NULL DEFAULT '',
  usage_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT '',
  system_prompt_cn TEXT NOT NULL DEFAULT '',
  system_prompt_en TEXT NOT NULL DEFAULT '',
  user_prompt_cn TEXT NOT NULL DEFAULT '',
  user_prompt_en TEXT NOT NULL DEFAULT '',
  negative_prompt_cn TEXT,
  negative_prompt_en TEXT,
  default_steps INTEGER,
  default_cfg REAL,
  default_sampler TEXT,
  default_scheduler TEXT,
  default_model TEXT
);
""",
    ),
    (
        "009_prompt_architecture",
        """
CREATE TABLE IF NOT EXISTS project_visual_specs (
  project_id TEXT PRIMARY KEY,
  spec_json TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS compiled_prompts (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_model TEXT NOT NULL,
  mode TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  guide_version TEXT NOT NULL,
  content TEXT NOT NULL,
  validation_json TEXT NOT NULL DEFAULT '{}',
  provider TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft',
  is_user_edited INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_compiled_prompt_source
ON compiled_prompts(project_id, source_type, source_id, mode, created_at);

ALTER TABLE assets ADD COLUMN candidate_group_id TEXT;
ALTER TABLE assets ADD COLUMN candidate_index INTEGER;
ALTER TABLE assets ADD COLUMN selection_status TEXT NOT NULL DEFAULT 'legacy';
CREATE INDEX IF NOT EXISTS idx_assets_candidate_group
ON assets(project_id, candidate_group_id, candidate_index);
""",
    ),
    (
        "010_storyboard_render",
        """
ALTER TABLE assets ADD COLUMN identity_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE scenes ADD COLUMN look_states_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE storyboard_frames ADD COLUMN accepted_render_attempt_id TEXT;

CREATE TABLE IF NOT EXISTS storyboard_render_requests (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  request_json TEXT NOT NULL,
  validation_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_storyboard_render_requests_frame
ON storyboard_render_requests(project_id, frame_id, created_at);

CREATE TABLE IF NOT EXISTS storyboard_render_attempts (
  id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  frame_id TEXT NOT NULL,
  asset_id TEXT,
  job_id TEXT,
  adapter TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  model_fingerprint TEXT NOT NULL DEFAULT '',
  seed INTEGER NOT NULL,
  is_degraded INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'queued',
  image_url TEXT,
  error_json TEXT NOT NULL DEFAULT '{}',
  rejection_reason TEXT,
  rejection_note TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_storyboard_render_attempts_frame
ON storyboard_render_attempts(project_id, frame_id, created_at);
""",
    ),
    (
        "011_identity_reference",
        """
ALTER TABLE storyboard_render_attempts
ADD COLUMN identity_evaluation_json TEXT NOT NULL DEFAULT '{}';
""",
    ),
]


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          id TEXT PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )
    applied = {row["id"] for row in conn.execute("SELECT id FROM schema_migrations")}
    from datetime import datetime

    for mid, sql in MIGRATE_SQL:
        if mid in applied:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
            (mid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
