PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS units (
  unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_code TEXT NOT NULL UNIQUE,
  unit_name TEXT NOT NULL,
  unit_type TEXT NOT NULL,
  contact_person TEXT,
  contact_phone TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  real_name TEXT NOT NULL,
  phone TEXT,
  password_hash TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '启用',
  unit_id INTEGER REFERENCES units(unit_id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
  project_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_code TEXT NOT NULL UNIQUE,
  project_name TEXT NOT NULL,
  location TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT '进行中',
  start_date TEXT,
  end_date TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_phases (
  phase_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  phase_name TEXT NOT NULL,
  phase_order INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT '未开始',
  start_date TEXT,
  end_date TEXT,
  UNIQUE (project_id, phase_order)
);

CREATE TABLE IF NOT EXISTS user_project_roles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  unit_id INTEGER REFERENCES units(unit_id) ON DELETE SET NULL,
  role TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (user_id, project_id, unit_id, role)
);

CREATE TABLE IF NOT EXISTS doc_types (
  doc_type_id INTEGER PRIMARY KEY AUTOINCREMENT,
  phase_id INTEGER NOT NULL REFERENCES project_phases(phase_id) ON DELETE CASCADE,
  doc_code TEXT NOT NULL,
  doc_name TEXT NOT NULL,
  responsible_unit_id INTEGER NOT NULL REFERENCES units(unit_id),
  is_required INTEGER NOT NULL DEFAULT 1 CHECK (is_required IN (0, 1)),
  need_approval INTEGER NOT NULL DEFAULT 0 CHECK (need_approval IN (0, 1)),
  file_formats TEXT,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (phase_id, doc_code)
);

CREATE TABLE IF NOT EXISTS documents (
  doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_type_id INTEGER NOT NULL REFERENCES doc_types(doc_type_id),
  project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  doc_no TEXT NOT NULL,
  title TEXT NOT NULL,
  current_version INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT '待上传',
  uploader_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  unit_id INTEGER REFERENCES units(unit_id) ON DELETE SET NULL,
  latest_file_path TEXT,
  file_hash TEXT,
  ocr_content TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (project_id, doc_no)
);

CREATE TABLE IF NOT EXISTS document_versions (
  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  version_no INTEGER NOT NULL,
  file_name TEXT NOT NULL,
  file_path TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  mime_type TEXT,
  file_hash TEXT NOT NULL,
  uploader_id INTEGER NOT NULL REFERENCES users(user_id),
  change_log TEXT,
  uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (doc_id, version_no)
);

CREATE TABLE IF NOT EXISTS approval_flows (
  approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  version_id INTEGER REFERENCES document_versions(version_id) ON DELETE SET NULL,
  approver_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  role TEXT,
  action TEXT NOT NULL DEFAULT '待审批',
  comment TEXT,
  status TEXT NOT NULL DEFAULT '待处理',
  action_time TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quality_alerts (
  alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id INTEGER REFERENCES documents(doc_id) ON DELETE CASCADE,
  project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  alert_level TEXT NOT NULL,
  alert_type TEXT NOT NULL,
  content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '待处理',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS piles (
  pile_id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  pile_no TEXT NOT NULL,
  bim_id TEXT,
  x_coord REAL,
  y_coord REAL,
  pile_type TEXT,
  design_depth REAL,
  status TEXT NOT NULL DEFAULT '待施工',
  UNIQUE (project_id, pile_no)
);

CREATE TABLE IF NOT EXISTS document_piles (
  doc_id INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  pile_id INTEGER NOT NULL REFERENCES piles(pile_id) ON DELETE CASCADE,
  PRIMARY KEY (doc_id, pile_id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
  project_id INTEGER REFERENCES projects(project_id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id INTEGER,
  details TEXT,
  ip_address TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY,
  csrf_token TEXT NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_project_roles_user ON user_project_roles(user_id, project_id);
CREATE INDEX IF NOT EXISTS idx_project_phases_project ON project_phases(project_id, phase_order);
CREATE INDEX IF NOT EXISTS idx_doc_types_phase ON doc_types(phase_id, doc_code);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_document_versions_doc ON document_versions(doc_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_approval_doc ON approval_flows(doc_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_project ON quality_alerts(project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
