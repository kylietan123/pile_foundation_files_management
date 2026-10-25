/**
 * 项目列表页验证：确认"我以···参与 / 责任等级"渲染正确。
 * 用法：node scripts/e2e_shot12.js <cdpPort> <outDir>
 */
const path = require('path')
const http = require('http')
const CDP = require('./cdp')

const FE = 'http://127.0.0.1:5173'

function req(method, p, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null
    const headers = {}
    if (token) headers.Authorization = `Bearer ${token}`
    if (data) {
      headers['Content-Type'] = 'application/json'
      headers['Content-Length'] = Buffer.byteLength(data)
    }
    const r = http.request({ host: '127.0.0.1', port: 8000, path: p, method, headers }, (res) => {
      let s = ''
      res.on('data', (d) => (s += d))
      res.on('end', () => { try { resolve(JSON.parse(s)) } catch (e) { reject(new Error(s.slice(0, 300))) } })
    })
    r.on('error', reject)
    if (data) r.write(data)
    r.end()
  })
}

;(async () => {
  const cdpPort = Number(process.argv[2])
  const outDir = process.argv[3]

  const login = await req('POST', '/api/v1/auth/login', null, {
    username: 'ouyuxin', password: 'Tjad@2026',
  })
  const { access_token, refresh_token } = login.data

  const ws = await CDP.openPage(cdpPort, 'about:blank', 500)
  await ws.send('Page.navigate', { url: FE + '/index.html' })
  await CDP.sleep(2500)
  await CDP.evalJS(ws, `
    localStorage.setItem('pile_lcm_access_token', ${JSON.stringify(access_token)});
    localStorage.setItem('pile_lcm_refresh_token', ${JSON.stringify(refresh_token)});
    'ok'`)

  await ws.send('Page.navigate', { url: FE + '/index.html#/projects' })
  await CDP.sleep(6500)

  const txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 900)`)
  console.log('---- 项目列表 ----')
  console.log(txt)
  console.log('----')

  // 抓控制台报错，确认没有运行期异常
  const errs = await CDP.evalJS(ws, `window.__probeErrors__ || 'none'`)
  console.log('页面报错:', errs)

  const h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  const size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1000), scale: 2,
    out: path.join(outDir, 'app-1-项目列表.png'),
  })
  console.log(`app-1-项目列表.png  ${(size / 1024).toFixed(0)} KB`)

  ws.close()
  process.exit(0)
})().catch((e) => { console.error('FAIL ' + e.message); process.exit(1) })
