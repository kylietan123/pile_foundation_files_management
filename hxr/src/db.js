'use strict';

const fs = require('fs');
const path = require('path');
const { DatabaseSync } = require('node:sqlite');

const DATA_DIR = path.join(__dirname, '..', 'data');
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

const db = new DatabaseSync(path.join(DATA_DIR, 'app.db'));

db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;

  CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
  );

  CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    location    TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    owner_id    INTEGER NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL,
    stage_id      INTEGER NOT NULL,
    party         TEXT NOT NULL,
    doc_type      TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    file_size     INTEGER NOT NULL DEFAULT 0,
    uploaded_by   INTEGER NOT NULL,
    uploaded_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
  );

  CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
  CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id);
`);

// 旧库迁移：早期版本没有 is_admin 字段，自动补上。
const userCols = db.prepare('PRAGMA table_info(users)').all();
if (!userCols.some((c) => c.name === 'is_admin')) {
  db.exec('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0');
}

// —— 用户 ——
const createUser = db.prepare(
  'INSERT INTO users (username, password_hash, display_name) VALUES (?, ?, ?)'
);
const getUserByUsername = db.prepare('SELECT * FROM users WHERE username = ?');
const getUserById = db.prepare('SELECT id, username, display_name, is_admin, created_at FROM users WHERE id = ?');

// —— 项目 ——
const createProject = db.prepare(
  'INSERT INTO projects (name, location, description, owner_id) VALUES (?, ?, ?, ?)'
);
const getProjectById = db.prepare('SELECT * FROM projects WHERE id = ?');
const listProjectsByOwner = db.prepare(
  'SELECT * FROM projects WHERE owner_id = ? ORDER BY updated_at DESC, id DESC'
);
const updateProject = db.prepare(
  `UPDATE projects SET name = ?, location = ?, description = ?,
   updated_at = datetime('now','localtime') WHERE id = ? AND owner_id = ?`
);
const deleteProject = db.prepare('DELETE FROM projects WHERE id = ? AND owner_id = ?');

// —— 文档 ——
const insertDocument = db.prepare(
  `INSERT INTO documents
   (project_id, stage_id, party, doc_type, original_name, stored_name, file_size, uploaded_by)
   VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
);
const getDocumentById = db.prepare('SELECT * FROM documents WHERE id = ?');
const listDocuments = db.prepare(
  `SELECT id, stage_id, party, doc_type, original_name, file_size, uploaded_at, uploaded_by
   FROM documents WHERE project_id = ? AND stage_id = ? ORDER BY id DESC`
);
const countDocumentsByStage = db.prepare(
  'SELECT stage_id, COUNT(*) AS n FROM documents WHERE project_id = ? GROUP BY stage_id'
);
const deleteDocument = db.prepare('DELETE FROM documents WHERE id = ?');

// —— 管理员用：全量用户 / 全量项目 ——
const listAllUsers = db.prepare(
  'SELECT id, username, display_name, is_admin, created_at FROM users ORDER BY id'
);
const setUserPassword = db.prepare('UPDATE users SET password_hash = ? WHERE id = ?');
const deleteUserRow = db.prepare('DELETE FROM users WHERE id = ?');
const listAllProjects = db.prepare(
  `SELECT p.*, u.display_name AS owner_name, u.username AS owner_username
   FROM projects p JOIN users u ON u.id = p.owner_id
   ORDER BY p.updated_at DESC, p.id DESC`
);

module.exports = {
  db,
  users: {
    create: (username, hash, displayName) =>
      createUser.run(username, hash, displayName),
    byUsername: (username) => getUserByUsername.get(username),
    byId: (id) => getUserById.get(id),
    all: () => listAllUsers.all(),
    resetPassword: (id, hash) => setUserPassword.run(hash, id),
    remove: (id) => deleteUserRow.run(id)
  },
  projects: {
    create: (name, location, description, ownerId) =>
      createProject.run(name, location, description, ownerId),
    byId: (id) => getProjectById.get(id),
    byOwner: (ownerId) => listProjectsByOwner.all(ownerId),
    all: () => listAllProjects.all(),
    update: (id, ownerId, { name, location, description }) =>
      updateProject.run(name, location, description, id, ownerId),
    remove: (id, ownerId) => deleteProject.run(id, ownerId)
  },
  documents: {
    insert: (projectId, stageId, party, docType, originalName, storedName, size, uploaderId) =>
      insertDocument.run(projectId, stageId, party, docType, originalName, storedName, size, uploaderId),
    byId: (id) => getDocumentById.get(id),
    list: (projectId, stageId) => listDocuments.all(projectId, stageId),
    countsByStage: (projectId) => {
      const rows = countDocumentsByStage.all(projectId);
      const map = {};
      for (const r of rows) map[r.stage_id] = r.n;
      return map;
    },
    remove: (id) => deleteDocument.run(id)
  }
};
