import { config } from './config.js';
import { hashToken, randomToken } from './security.js';
import { HttpError, assertSameOrigin, parseCookies } from './http.js';

const SESSION_SECONDS = config.sessionHours * 60 * 60;

export function createSession(db, userId) {
  db.prepare('DELETE FROM sessions WHERE expires_at <= CURRENT_TIMESTAMP').run();
  const token = randomToken();
  const csrfToken = randomToken(24);
  const expiresAt = new Date(Date.now() + SESSION_SECONDS * 1000)
    .toISOString()
    .slice(0, 19)
    .replace('T', ' ');
  db.prepare(`
    INSERT INTO sessions (token_hash, csrf_token, user_id, expires_at)
    VALUES (?, ?, ?, ?)
  `).run(hashToken(token), csrfToken, userId, expiresAt);
  return { token, csrfToken, maxAgeSeconds: SESSION_SECONDS };
}

export function getSession(req, db) {
  const token = parseCookies(req)[config.cookieName];
  if (!token) return null;
  const session = db.prepare(`
    SELECT
      s.token_hash,
      s.csrf_token,
      s.expires_at,
      u.user_id,
      u.username,
      u.real_name,
      u.phone,
      u.status,
      u.unit_id,
      un.unit_code,
      un.unit_name,
      un.unit_type
    FROM sessions s
    JOIN users u ON u.user_id = s.user_id
    LEFT JOIN units un ON un.unit_id = u.unit_id
    WHERE s.token_hash = ? AND s.expires_at > CURRENT_TIMESTAMP
  `).get(hashToken(token));
  if (!session || session.status !== '启用') return null;
  return session;
}

export function requireSession(req, db) {
  const session = getSession(req, db);
  if (!session) throw new HttpError(401, '请先登录', 'UNAUTHORIZED');
  return session;
}

export function requireCsrf(req, session) {
  assertSameOrigin(req);
  const provided = String(req.headers['x-csrf-token'] || '');
  if (!provided || provided !== session.csrf_token) {
    throw new HttpError(403, '安全令牌无效，请刷新页面后重试', 'INVALID_CSRF');
  }
}

export function destroySession(req, db) {
  const token = parseCookies(req)[config.cookieName];
  if (token) db.prepare('DELETE FROM sessions WHERE token_hash = ?').run(hashToken(token));
}
