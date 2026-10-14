'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const jwt = require('jsonwebtoken');

const DATA_DIR = path.join(__dirname, '..', 'data');
const SECRET_FILE = path.join(DATA_DIR, '.secret');

// 首次启动时生成一个随机密钥并持久化，保证重启后已登录用户的 token 依然有效。
function loadSecret() {
  if (fs.existsSync(SECRET_FILE)) {
    return fs.readFileSync(SECRET_FILE, 'utf8').trim();
  }
  const secret = crypto.randomBytes(48).toString('hex');
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(SECRET_FILE, secret, { mode: 0o600 });
  return secret;
}

const JWT_SECRET = loadSecret();
const TOKEN_COOKIE = 'token';

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString('hex');
  const hash = crypto.scryptSync(password, salt, 64).toString('hex');
  return `${salt}:${hash}`;
}

function verifyPassword(password, stored) {
  if (!stored || !stored.includes(':')) return false;
  const [salt, hash] = stored.split(':');
  const test = crypto.scryptSync(password, salt, 64);
  const expected = Buffer.from(hash, 'hex');
  return test.length === expected.length && crypto.timingSafeEqual(test, expected);
}

function signToken(userId) {
  return jwt.sign({ uid: userId }, JWT_SECRET, { expiresIn: '30d' });
}

// 登录鉴权中间件：校验 cookie 中的 JWT 并把当前用户挂到 req.user。
function authRequired(req, res, next) {
  const token = req.cookies && req.cookies[TOKEN_COOKIE];
  if (!token) return res.status(401).json({ error: '未登录' });
  try {
    const payload = jwt.verify(token, JWT_SECRET);
    const user = require('./db').users.byId(payload.uid);
    if (!user) return res.status(401).json({ error: '用户不存在' });
    req.user = user;
    next();
  } catch (e) {
    return res.status(401).json({ error: '登录已过期，请重新登录' });
  }
}

// 管理员鉴权中间件：需在 authRequired 之后使用。
function adminRequired(req, res, next) {
  if (!req.user.is_admin) return res.status(403).json({ error: '需要管理员权限' });
  next();
}

module.exports = {
  JWT_SECRET,
  TOKEN_COOKIE,
  hashPassword,
  verifyPassword,
  signToken,
  authRequired,
  adminRequired
};
