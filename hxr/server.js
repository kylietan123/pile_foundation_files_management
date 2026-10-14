'use strict';

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');

const express = require('express');
const cookieParser = require('cookie-parser');
const multer = require('multer');

const { db, users, projects, documents } = require('./src/db');
const { TOKEN_COOKIE, hashPassword, verifyPassword, signToken, authRequired, adminRequired } = require('./src/auth');
const STAGES = require('./config/stages');

// 统一返回给前端的用户对象（camelCase）。
function toClientUser(u) {
  return {
    id: u.id,
    username: u.username,
    displayName: u.display_name,
    isAdmin: !!u.is_admin,
    createdAt: u.created_at
  };
}

// 内置管理员账号（首次启动时创建）。
// 初始密码通过环境变量 ADMIN_PASSWORD 指定；未指定则随机生成并在控制台打印，
// 避免把真实密码写死在代码里（尤其是不宜提交到公开仓库）。
function seedAdmin() {
  const username = process.env.ADMIN_USERNAME || 'haoxirui';
  const displayName = process.env.ADMIN_DISPLAY_NAME || '郝兮睿';
  let admin = users.byUsername(username);
  if (!admin) {
    const password = process.env.ADMIN_PASSWORD || crypto.randomBytes(8).toString('hex');
    users.create(username, hashPassword(password), displayName);
    admin = users.byUsername(username);
    db.prepare('UPDATE users SET is_admin = 1 WHERE id = ?').run(admin.id);
    if (!process.env.ADMIN_PASSWORD) {
      console.log('');
      console.log(`[管理员初始化] 账号「${username}」已创建，初始密码：${password}`);
      console.log('请登录后立即在右上角「修改密码」中更改初始密码。');
      console.log('（提示：可在启动前通过环境变量 ADMIN_PASSWORD 指定初始密码）');
      console.log('');
    }
  } else {
    db.prepare('UPDATE users SET is_admin = 1 WHERE id = ?').run(admin.id);
  }
}
seedAdmin();

const app = express();
const PORT = process.env.PORT || 3000;

const UPLOAD_DIR = path.join(__dirname, 'uploads');
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

app.use(express.json({ limit: '2mb' }));
app.use(cookieParser());
app.use(express.static(path.join(__dirname, 'public')));

// —— 文件上传（multer）——
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const dir = path.join(UPLOAD_DIR, String(req.params.id));
    fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (req, file, cb) => {
    const stored = crypto.randomBytes(12).toString('hex') + path.extname(file.originalname);
    cb(null, stored);
  }
});
const upload = multer({
  storage,
  limits: { fileSize: 200 * 1024 * 1024 } // 单文件最大 200MB
});

// busboy/multer 按 latin1 解码 multipart 的 filename 参数，中文文件名会变成乱码，
// 这里把 latin1 字符串还原回正确的 UTF-8。
function decodeOriginalName(name) {
  return Buffer.from(name, 'latin1').toString('utf8');
}

function getStageById(id) {
  return STAGES.find((s) => s.id === Number(id));
}

// —— 鉴权相关 ——
app.post('/api/auth/register', (req, res) => {
  const { username, password, displayName } = req.body || {};
  const name = String(username || '').trim();
  const pwd = String(password || '');
  const disp = String(displayName || '').trim() || name;

  if (!/^[a-zA-Z0-9_一-龥]{2,20}$/.test(name)) {
    return res.status(400).json({ error: '用户名需为 2-20 位字母、数字、下划线或中文' });
  }
  if (pwd.length < 6) {
    return res.status(400).json({ error: '密码至少 6 位' });
  }
  if (users.byUsername(name)) {
    return res.status(409).json({ error: '该用户名已被注册' });
  }

  users.create(name, hashPassword(pwd), disp);
  const user = users.byUsername(name);
  res.cookie(TOKEN_COOKIE, signToken(user.id), {
    httpOnly: true, sameSite: 'lax', maxAge: 30 * 24 * 3600 * 1000
  });
  res.json({ user: toClientUser(user) });
});

app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  const user = users.byUsername(String(username || '').trim());
  if (!user || !verifyPassword(String(password || ''), user.password_hash)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }
  res.cookie(TOKEN_COOKIE, signToken(user.id), {
    httpOnly: true, sameSite: 'lax', maxAge: 30 * 24 * 3600 * 1000
  });
  res.json({ user: toClientUser(user) });
});

app.post('/api/auth/logout', (req, res) => {
  res.clearCookie(TOKEN_COOKIE);
  res.json({ ok: true });
});

app.get('/api/auth/me', authRequired, (req, res) => {
  res.json({ user: toClientUser(req.user) });
});

app.post('/api/auth/password', authRequired, (req, res) => {
  const { oldPassword, newPassword } = req.body || {};
  const full = users.byUsername(req.user.username);
  if (!verifyPassword(String(oldPassword || ''), full.password_hash)) {
    return res.status(400).json({ error: '原密码错误' });
  }
  const pwd = String(newPassword || '');
  if (pwd.length < 6) return res.status(400).json({ error: '新密码至少 6 位' });
  users.resetPassword(full.id, hashPassword(pwd));
  res.json({ ok: true });
});

// —— 阶段模板 ——
app.get('/api/stages', authRequired, (req, res) => {
  res.json({ stages: STAGES });
});

// —— 项目 CRUD（仅限本人项目）——
app.get('/api/projects', authRequired, (req, res) => {
  const list = req.user.is_admin ? projects.all() : projects.byOwner(req.user.id);
  res.json({ projects: list });
});

app.post('/api/projects', authRequired, (req, res) => {
  const name = String((req.body || {}).name || '').trim();
  if (!name) return res.status(400).json({ error: '项目名称不能为空' });
  const location = String((req.body || {}).location || '').trim();
  const description = String((req.body || {}).description || '').trim();
  const info = projects.create(name, location, description, req.user.id);
  res.json({ project: projects.byId(Number(info.lastInsertRowid)) });
});

function loadProject(req, res) {
  const project = projects.byId(Number(req.params.id));
  if (!project) {
    res.status(404).json({ error: '项目不存在' });
    return null;
  }
  if (project.owner_id !== req.user.id && !req.user.is_admin) {
    res.status(403).json({ error: '无权访问该项目' });
    return null;
  }
  return project;
}

app.get('/api/projects/:id', authRequired, (req, res) => {
  const project = loadProject(req, res);
  if (!project) return;
  res.json({ project, stats: documents.countsByStage(project.id) });
});

app.put('/api/projects/:id', authRequired, (req, res) => {
  const project = loadProject(req, res);
  if (!project) return;
  const name = String((req.body || {}).name || '').trim();
  if (!name) return res.status(400).json({ error: '项目名称不能为空' });
  projects.update(project.id, req.user.id, {
    name,
    location: String((req.body || {}).location || '').trim(),
    description: String((req.body || {}).description || '').trim()
  });
  res.json({ project: projects.byId(project.id) });
});

app.delete('/api/projects/:id', authRequired, (req, res) => {
  const project = loadProject(req, res);
  if (!project) return;
  // 同时删除该项目下的所有文件与记录
  const docs = db.prepare('SELECT stored_name FROM documents WHERE project_id = ?').all(project.id);
  for (const d of docs) {
    const p = path.join(UPLOAD_DIR, String(project.id), d.stored_name);
    try { if (fs.existsSync(p)) fs.unlinkSync(p); } catch (e) { /* ignore */ }
  }
  projects.remove(project.id, req.user.id);
  try { fs.rmSync(path.join(UPLOAD_DIR, String(project.id)), { recursive: true, force: true }); } catch (e) { /* ignore */ }
  res.json({ ok: true });
});

// —— 文档：列表 / 上传 / 下载 / 删除 ——
app.get('/api/projects/:id/documents', authRequired, (req, res) => {
  const project = loadProject(req, res);
  if (!project) return;
  const stageId = Number(req.query.stage);
  const docs = stageId ? documents.list(project.id, stageId) : [];
  res.json({ documents: docs });
});

app.post('/api/projects/:id/documents', authRequired, upload.single('file'), (req, res) => {
  const project = loadProject(req, res);
  if (!project) return;
  if (!req.file) return res.status(400).json({ error: '未选择文件' });

  const stageId = Number(req.body.stageId);
  const party = String(req.body.party || '').trim();
  const docType = String(req.body.docType || '').trim();
  if (!getStageById(stageId) || !party || !docType) {
    return res.status(400).json({ error: '缺少阶段 / 单位 / 文档类型信息' });
  }

  const originalName = decodeOriginalName(req.file.originalname);
  documents.insert(
    project.id, stageId, party, docType, originalName, req.file.filename,
    req.file.size, req.user.id
  );
  res.json({ ok: true });
});

app.get('/api/documents/:docId/download', authRequired, (req, res) => {
  const doc = documents.byId(Number(req.params.docId));
  if (!doc) return res.status(404).json({ error: '文档不存在' });
  const project = projects.byId(doc.project_id);
  if (!project || project.owner_id !== req.user.id) {
    return res.status(403).json({ error: '无权下载该文档' });
  }
  const filePath = path.join(UPLOAD_DIR, String(doc.project_id), doc.stored_name);
  if (!fs.existsSync(filePath)) return res.status(404).json({ error: '文件已丢失' });

  const encoded = encodeURIComponent(doc.original_name);
  res.setHeader('Content-Disposition',
    `attachment; filename*=UTF-8''${encoded}`);
  res.sendFile(filePath);
});

app.delete('/api/documents/:docId', authRequired, (req, res) => {
  const doc = documents.byId(Number(req.params.docId));
  if (!doc) return res.status(404).json({ error: '文档不存在' });
  const project = projects.byId(doc.project_id);
  if (!project || project.owner_id !== req.user.id) {
    return res.status(403).json({ error: '无权删除该文档' });
  }
  const filePath = path.join(UPLOAD_DIR, String(doc.project_id), doc.stored_name);
  try { if (fs.existsSync(filePath)) fs.unlinkSync(filePath); } catch (e) { /* ignore */ }
  documents.remove(doc.id);
  res.json({ ok: true });
});

// —— 用户管理（仅管理员）——
app.get('/api/users', authRequired, adminRequired, (req, res) => {
  res.json({ users: users.all().map(toClientUser) });
});

app.post('/api/users/:id/reset-password', authRequired, adminRequired, (req, res) => {
  const target = users.byId(Number(req.params.id));
  if (!target) return res.status(404).json({ error: '用户不存在' });
  const pwd = String((req.body || {}).password || '');
  if (pwd.length < 6) return res.status(400).json({ error: '密码至少 6 位' });
  users.resetPassword(target.id, hashPassword(pwd));
  res.json({ ok: true });
});

app.delete('/api/users/:id', authRequired, adminRequired, (req, res) => {
  const target = users.byId(Number(req.params.id));
  if (!target) return res.status(404).json({ error: '用户不存在' });
  if (target.id === req.user.id) return res.status(400).json({ error: '不能删除自己的账号' });

  // 1) 先删除该用户上传过的所有文档（含上传到他人项目中的），解除 uploaded_by 外键
  const upDocs = db.prepare('SELECT id, project_id, stored_name FROM documents WHERE uploaded_by = ?').all(target.id);
  for (const d of upDocs) {
    try { fs.unlinkSync(path.join(UPLOAD_DIR, String(d.project_id), d.stored_name)); } catch (e) { /* ignore */ }
    db.prepare('DELETE FROM documents WHERE id = ?').run(d.id);
  }
  // 2) 清理其名下项目的文件目录
  const projIds = db.prepare('SELECT id FROM projects WHERE owner_id = ?').all(target.id);
  for (const p of projIds) {
    try { fs.rmSync(path.join(UPLOAD_DIR, String(p.id)), { recursive: true, force: true }); } catch (e) { /* ignore */ }
  }
  // 3) 删除用户（外键级联删除其项目与项目内文档）
  users.remove(target.id);
  res.json({ ok: true });
});

// —— 兜底：前端 SPA 页面 ——
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// 统一错误处理
app.use((err, req, res, next) => {
  console.error(err);
  if (err && err.code === 'LIMIT_FILE_SIZE') {
    return res.status(400).json({ error: '文件过大，单文件不能超过 200MB' });
  }
  res.status(500).json({ error: '服务器内部错误' });
});

app.listen(PORT, () => {
  console.log(`桩基工程文档平台已启动：http://localhost:${PORT}`);
});
