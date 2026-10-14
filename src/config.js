import path from 'node:path';

const rootDir = path.resolve(import.meta.dirname, '..');

function envInt(name, fallback) {
  const value = Number.parseInt(process.env[name] ?? '', 10);
  return Number.isFinite(value) ? value : fallback;
}

function resolveFromRoot(value) {
  return path.isAbsolute(value) ? value : path.resolve(rootDir, value);
}

export const config = {
  rootDir,
  publicDir: path.join(rootDir, 'public'),
  host: process.env.HOST || '127.0.0.1',
  port: envInt('PORT', 3000),
  dbPath: resolveFromRoot(process.env.DB_PATH || './data/pile-platform.db'),
  uploadDir: resolveFromRoot(process.env.UPLOAD_DIR || './data/uploads'),
  sessionHours: envInt('SESSION_HOURS', 8),
  maxUploadBytes: envInt('MAX_UPLOAD_MB', 200) * 1024 * 1024,
  cookieName: 'pile_session',
  isProduction: process.env.NODE_ENV === 'production',
};
