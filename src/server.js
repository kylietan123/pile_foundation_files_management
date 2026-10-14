import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { config } from './config.js';
import { openDatabase } from './db/database.js';
import {
  HttpError,
  clearSessionCookie,
  getClientIp,
  readFormData,
  readJson,
  sendJson,
  sendNoContent,
  sessionCookie,
} from './http.js';
import {
  createSession,
  destroySession,
  requireCsrf,
  requireSession,
} from './auth.js';
import { verifyPassword } from './security.js';
import { getUserProjectAccess, writeAuditLog } from './permissions.js';
import {
  addDocumentVersion,
  createDocument,
  getDashboard,
  getDocumentDetail,
  getPhaseDetails,
  getVersionFile,
  listAccessibleProjects,
  listAuditLogs,
} from './data-service.js';

const db = openDatabase();

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

function pathMatch(pathname, pattern) {
  const match = pathname.match(pattern);
  return match ? match.slice(1).map(Number) : null;
}

function requirePositiveIds(...ids) {
  if (ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) {
    throw new HttpError(400, '资源编号不正确', 'INVALID_ID');
  }
}

function mePayload(db, session) {
  return {
    user: {
      user_id: Number(session.user_id),
      username: session.username,
      real_name: session.real_name,
      phone: session.phone,
      unit_id: session.unit_id ? Number(session.unit_id) : null,
      unit_code: session.unit_code,
      unit_name: session.unit_name,
      unit_type: session.unit_type,
    },
    projects: listAccessibleProjects(db, Number(session.user_id)),
    csrf_token: session.csrf_token,
  };
}

async function handleApi(req, res, url) {
  const { pathname, searchParams } = url;
  const method = req.method;

  if (method === 'GET' && pathname === '/api/health') {
    return sendJson(res, 200, { ok: true, time: new Date().toISOString() });
  }

  if (method === 'POST' && pathname === '/api/auth/login') {
    const body = await readJson(req);
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    const user = db.prepare(`
      SELECT
        u.user_id, u.username, u.real_name, u.phone, u.status, u.password_hash,
        u.unit_id, un.unit_code, un.unit_name, un.unit_type
      FROM users u
      LEFT JOIN units un ON un.unit_id = u.unit_id
      WHERE u.username = ?
    `).get(username);
    if (!user || user.status !== '启用' || !verifyPassword(password, user.password_hash)) {
      throw new HttpError(401, '账号或密码不正确', 'INVALID_CREDENTIALS');
    }
    const session = createSession(db, Number(user.user_id));
    const sessionRow = {
      ...user,
      user_id: Number(user.user_id),
      csrf_token: session.csrfToken,
    };
    res.setHeader('Set-Cookie', sessionCookie(
      config.cookieName,
      session.token,
      session.maxAgeSeconds,
      config.isProduction,
    ));
    return sendJson(res, 200, mePayload(db, sessionRow));
  }

  if (method === 'POST' && pathname === '/api/auth/logout') {
    const session = requireSession(req, db);
    requireCsrf(req, session);
    destroySession(req, db);
    res.setHeader('Set-Cookie', clearSessionCookie(config.cookieName, config.isProduction));
    return sendNoContent(res);
  }

  if (method === 'GET' && pathname === '/api/me') {
    const session = requireSession(req, db);
    return sendJson(res, 200, mePayload(db, session));
  }

  if (method === 'GET' && pathname === '/api/projects') {
    const session = requireSession(req, db);
    return sendJson(res, 200, { projects: listAccessibleProjects(db, Number(session.user_id)) });
  }

  let ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/dashboard$/);
  if (method === 'GET' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    return sendJson(res, 200, getDashboard(db, Number(session.user_id), ids[0]));
  }

  ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/phases\/(\d+)$/);
  if (method === 'GET' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    return sendJson(res, 200, getPhaseDetails(db, Number(session.user_id), ids[0], ids[1]));
  }

  ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/audit$/);
  if (method === 'GET' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    return sendJson(res, 200, {
      logs: listAuditLogs(db, Number(session.user_id), ids[0], searchParams.get('limit')),
    });
  }

  ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/documents\/(\d+)$/);
  if (method === 'GET' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    return sendJson(res, 200, getDocumentDetail(db, Number(session.user_id), ids[0], ids[1]));
  }

  ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/document-types\/(\d+)\/documents$/);
  if (method === 'POST' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    requireCsrf(req, session);
    const formData = await readFormData(req, config.maxUploadBytes);
    const result = await createDocument(db, session, ids[0], ids[1], formData);
    return sendJson(res, 201, result);
  }

  ids = pathMatch(pathname, /^\/api\/projects\/(\d+)\/documents\/(\d+)\/versions$/);
  if (method === 'POST' && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    requireCsrf(req, session);
    const formData = await readFormData(req, config.maxUploadBytes);
    const result = await addDocumentVersion(db, session, ids[0], ids[1], formData);
    return sendJson(res, 201, result);
  }

  ids = pathMatch(pathname, /^\/api\/files\/(\d+)$/);
  if ((method === 'GET' || method === 'HEAD') && ids) {
    requirePositiveIds(...ids);
    const session = requireSession(req, db);
    const file = getVersionFile(db, Number(session.user_id), ids[0]);
    return serveStoredFile(req, res, file, searchParams.get('download') === '1');
  }

  throw new HttpError(404, '接口不存在', 'NOT_FOUND');
}

function serveStoredFile(req, res, file, download) {
  if (!fs.existsSync(file.absolute_path)) {
    throw new HttpError(404, '文件实体不存在或已被移除', 'FILE_NOT_FOUND');
  }
  const stat = fs.statSync(file.absolute_path);
  const range = req.headers.range;
  const encodedName = encodeURIComponent(file.file_name);
  const disposition = download ? 'attachment' : 'inline';
  const commonHeaders = {
    'Content-Type': file.mime_type || 'application/octet-stream',
    'Content-Disposition': `${disposition}; filename*=UTF-8''${encodedName}`,
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'private, max-age=300',
    'Accept-Ranges': 'bytes',
  };

  if (range) {
    const match = range.match(/^bytes=(\d*)-(\d*)$/);
    if (match) {
      const start = match[1] ? Number(match[1]) : 0;
      const end = match[2] ? Number(match[2]) : stat.size - 1;
      if (start <= end && start < stat.size) {
        const safeEnd = Math.min(end, stat.size - 1);
        res.writeHead(206, {
          ...commonHeaders,
          'Content-Range': `bytes ${start}-${safeEnd}/${stat.size}`,
          'Content-Length': safeEnd - start + 1,
        });
        if (req.method === 'HEAD') return res.end();
        return fs.createReadStream(file.absolute_path, { start, end: safeEnd }).pipe(res);
      }
    }
  }

  res.writeHead(200, {
    ...commonHeaders,
    'Content-Length': stat.size,
  });
  if (req.method === 'HEAD') return res.end();
  return fs.createReadStream(file.absolute_path).pipe(res);
}

function serveStatic(req, res, url) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    throw new HttpError(405, '请求方法不支持', 'METHOD_NOT_ALLOWED');
  }

  let pathname;
  try {
    pathname = decodeURIComponent(url.pathname);
  } catch {
    throw new HttpError(400, '路径格式不正确', 'INVALID_PATH');
  }
  if (pathname === '/') pathname = '/index.html';

  const absolutePath = path.resolve(config.publicDir, `.${pathname}`);
  if (!absolutePath.startsWith(`${config.publicDir}${path.sep}`)) {
    throw new HttpError(403, '禁止访问该路径', 'PATH_FORBIDDEN');
  }
  if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
    throw new HttpError(404, '页面不存在', 'NOT_FOUND');
  }

  const stat = fs.statSync(absolutePath);
  res.writeHead(200, {
    'Content-Type': MIME_TYPES[path.extname(absolutePath).toLowerCase()] || 'application/octet-stream',
    'Content-Length': stat.size,
    'Cache-Control': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
  });
  if (req.method === 'HEAD') return res.end();
  return fs.createReadStream(absolutePath).pipe(res);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || `${config.host}:${config.port}`}`);
  try {
    if (url.pathname.startsWith('/api/')) {
      await handleApi(req, res, url);
    } else {
      serveStatic(req, res, url);
    }
  } catch (error) {
    const status = error instanceof HttpError ? error.status : 500;
    const message = error instanceof HttpError ? error.message : '服务器内部错误';
    const code = error instanceof HttpError ? error.code : 'INTERNAL_ERROR';
    if (status >= 500) console.error(error);
    if (!res.headersSent) {
      sendJson(res, status, { error: message, code });
    } else {
      res.destroy();
    }
  }
});

server.listen(config.port, config.host, () => {
  console.log(`桩基工程全过程管理平台已启动：http://${config.host}:${config.port}`);
  console.log(`数据库：${config.dbPath}`);
  console.log('演示账号：admin / owner_viewer / contractor / pile_subcontractor / supervisor / testing');
  console.log('演示密码：Demo@123456');
});

function shutdown() {
  server.close(() => {
    db.close();
    process.exit(0);
  });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
