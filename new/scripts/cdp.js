// 最小 CDP 驱动（共用模块）
const net = require('net');
const crypto = require('crypto');
const http = require('http');

class WS {
  constructor(url) {
    const u = new URL(url);
    this.host = u.hostname;
    this.port = u.port || 80;
    this.pathname = u.pathname + (u.search || '');
    this.buf = Buffer.alloc(0);
    this.handlers = new Map();
    this.listeners = [];
    this.nextId = 1;
    this.ready = new Promise((res, rej) => { this._res = res; this._rej = rej; });
  }
  connect() {
    const key = crypto.randomBytes(16).toString('base64');
    this.sock = net.connect(this.port, this.host, () => {
      this.sock.write(
        `GET ${this.pathname} HTTP/1.1\r\nHost: ${this.host}:${this.port}\r\n` +
        `Upgrade: websocket\r\nConnection: Upgrade\r\n` +
        `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`
      );
    });
    this.sock.on('data', (d) => this._onData(d));
    this.sock.on('error', (e) => this._rej(e));
    return this;
  }
  _onData(d) {
    this.buf = Buffer.concat([this.buf, d]);
    if (!this.upgraded) {
      const i = this.buf.indexOf('\r\n\r\n');
      if (i < 0) return;
      const head = this.buf.slice(0, i).toString();
      if (!/101/.test(head.split('\r\n')[0])) return this._rej(new Error('握手失败: ' + head.split('\r\n')[0]));
      this.upgraded = true;
      this.buf = this.buf.slice(i + 4);
      this._res();
    }
    this._drain();
  }
  _drain() {
    for (;;) {
      const b = this.buf;
      if (b.length < 2) return;
      const op = b[0] & 0x0f;
      let len = b[1] & 0x7f, off = 2;
      if (len === 126) { if (b.length < 4) return; len = b.readUInt16BE(2); off = 4; }
      else if (len === 127) { if (b.length < 10) return; len = Number(b.readBigUInt64BE(2)); off = 10; }
      const masked = (b[1] & 0x80) !== 0;
      let mask;
      if (masked) { if (b.length < off + 4) return; mask = b.slice(off, off + 4); off += 4; }
      if (b.length < off + len) return;
      let payload = b.slice(off, off + len);
      if (masked) { const c = Buffer.from(payload); for (let i = 0; i < c.length; i++) c[i] ^= mask[i % 4]; payload = c; }
      this.buf = b.slice(off + len);
      if (op === 1) { try { this._onMessage(JSON.parse(payload.toString('utf8'))); } catch (e) {} }
      else if (op === 8) { this.sock.end(); return; }
      else if (op === 9) { this._frame(10, payload); }
    }
  }
  _onMessage(m) {
    if (m.id && this.handlers.has(m.id)) {
      const h = this.handlers.get(m.id);
      this.handlers.delete(m.id);
      if (m.error) h.reject(new Error(JSON.stringify(m.error))); else h.resolve(m.result);
    }
    this.listeners.forEach((f) => { try { f(m); } catch (e) {} });
  }
  _frame(op, payload) {
    const p = Buffer.isBuffer(payload) ? payload : Buffer.from(payload || '', 'utf8');
    const mask = crypto.randomBytes(4);
    let head;
    if (p.length < 126) head = Buffer.from([0x80 | op, 0x80 | p.length]);
    else if (p.length < 65536) { head = Buffer.alloc(4); head[0] = 0x80 | op; head[1] = 0x80 | 126; head.writeUInt16BE(p.length, 2); }
    else { head = Buffer.alloc(10); head[0] = 0x80 | op; head[1] = 0x80 | 127; head.writeBigUInt64BE(BigInt(p.length), 2); }
    const c = Buffer.from(p);
    for (let i = 0; i < c.length; i++) c[i] ^= mask[i % 4];
    this.sock.write(Buffer.concat([head, mask, c]));
  }
  send(method, params) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.handlers.set(id, { resolve, reject });
      this._frame(1, JSON.stringify({ id, method, params: params || {} }));
    });
  }
  close() { try { this._frame(8, Buffer.alloc(0)); this.sock.end(); } catch (e) {} }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function httpJson(port, p, method = 'GET') {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, path: p, method }, (res) => {
      let s = '';
      res.on('data', (d) => (s += d));
      res.on('end', () => { try { resolve(JSON.parse(s)); } catch (e) { reject(new Error(s.slice(0, 200))); } });
    });
    req.on('error', reject);
    req.end();
  });
}

function toFileUrl(p) { return 'file:///' + p.replace(/\\/g, '/').replace(/^\//, ''); }

async function openPage(port, filePath, settleMs = 1500) {
  const t = await httpJson(port, '/json/new?' + encodeURIComponent(toFileUrl(filePath)), 'PUT');
  if (!t.webSocketDebuggerUrl) throw new Error('无法创建 target: ' + JSON.stringify(t).slice(0, 200));
  const ws = new WS(t.webSocketDebuggerUrl).connect();
  await ws.ready;
  await ws.send('Page.enable');
  await ws.send('Runtime.enable');
  await sleep(settleMs);
  return ws;
}

async function evalJS(ws, expr) {
  const r = await ws.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error('JS 异常: ' + JSON.stringify(r.exceptionDetails).slice(0, 500));
  return r.result.value;
}

async function shot(ws, { x = 0, y = 0, width, height, scale = 2, out }) {
  await ws.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: scale, mobile: false });
  await sleep(450);
  const r = await ws.send('Page.captureScreenshot', {
    format: 'png', captureBeyondViewport: true,
    clip: { x, y, width, height, scale },
  });
  require('fs').writeFileSync(out, Buffer.from(r.data, 'base64'));
  return require('fs').statSync(out).size;
}

module.exports = { WS, sleep, httpJson, toFileUrl, openPage, evalJS, shot };
