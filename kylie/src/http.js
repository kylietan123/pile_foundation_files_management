import { Readable } from 'node:stream';

export class HttpError extends Error {
  constructor(status, message, code = 'REQUEST_ERROR') {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function sendJson(res, status, payload, headers = {}) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
    ...headers,
  });
  res.end(body);
}

export function sendNoContent(res, headers = {}) {
  res.writeHead(204, headers);
  res.end();
}

export async function readJson(req, maxBytes = 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBytes) throw new HttpError(413, '请求内容过大', 'BODY_TOO_LARGE');
    chunks.push(chunk);
  }

  if (chunks.length === 0) return {};
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  } catch {
    throw new HttpError(400, 'JSON 格式不正确', 'INVALID_JSON');
  }
}

export async function readFormData(req, maxBytes) {
  const contentLength = Number.parseInt(req.headers['content-length'] || '0', 10);
  if (Number.isFinite(contentLength) && contentLength > maxBytes) {
    throw new HttpError(413, `上传内容超过 ${Math.round(maxBytes / 1024 / 1024)} MB`, 'FILE_TOO_LARGE');
  }

  try {
    const request = new Request('http://localhost', {
      method: req.method,
      headers: req.headers,
      body: Readable.toWeb(req),
      duplex: 'half',
    });
    return await request.formData();
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(400, '上传表单解析失败', 'INVALID_MULTIPART');
  }
}

export function parseCookies(req) {
  const cookies = {};
  for (const part of String(req.headers.cookie || '').split(';')) {
    const index = part.indexOf('=');
    if (index === -1) continue;
    const key = part.slice(0, index).trim();
    const value = part.slice(index + 1).trim();
    if (key) cookies[key] = decodeURIComponent(value);
  }
  return cookies;
}

export function sessionCookie(name, token, maxAgeSeconds, secure = false) {
  const parts = [
    `${name}=${encodeURIComponent(token)}`,
    'HttpOnly',
    'SameSite=Lax',
    'Path=/',
    `Max-Age=${maxAgeSeconds}`,
  ];
  if (secure) parts.push('Secure');
  return parts.join('; ');
}

export function clearSessionCookie(name, secure = false) {
  return sessionCookie(name, '', 0, secure);
}

export function getClientIp(req) {
  const forwarded = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  return forwarded || req.socket.remoteAddress || null;
}

export function assertSameOrigin(req) {
  const origin = req.headers.origin;
  if (!origin) return;
  const host = req.headers.host;
  try {
    const originHost = new URL(origin).host;
    if (host && originHost !== host) {
      throw new HttpError(403, '请求来源校验失败', 'INVALID_ORIGIN');
    }
  } catch (error) {
    if (error instanceof HttpError) throw error;
    throw new HttpError(403, '请求来源校验失败', 'INVALID_ORIGIN');
  }
}
