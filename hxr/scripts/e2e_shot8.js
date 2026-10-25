/**
 * 单位主体改造后的页面验证截图。
 * 用法：node scripts/e2e_shot8.js <cdpPort> <outDir>
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

  // 用设计单位账号：能验证"我以设计单位参与 / 主办阶段=设计"
  const login = await req('POST', '/api/v1/auth/login', null, {
    username: 'ouyuxin', password: 'Tjad@2026',
  })
  const { access_token, refresh_token } = login.data
  const me = await req('GET', '/api/v1/auth/me', access_token)
  console.log('登录用户:', me.data.name, ' 超管:', me.data.is_superuser)
  for (const m of me.data.memberships) {
    console.log(`  ${m.project_name} → ${m.unit_label} / ${m.responsibility_label} / 主办 ${m.primary_stages}`)
  }

  const ws = await CDP.openPage(cdpPort, 'about:blank', 500)
  await ws.send('Page.navigate', { url: FE + '/index.html' })
  await CDP.sleep(2500)
  await CDP.evalJS(ws, `
    localStorage.setItem('pile_lcm_access_token', ${JSON.stringify(access_token)});
    localStorage.setItem('pile_lcm_refresh_token', ${JSON.stringify(refresh_token)});
    'ok'`)

  // ---------- 项目列表 ----------
  await ws.send('Page.navigate', { url: FE + '/index.html#/projects' })
  await CDP.sleep(6000)
  let txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 700)`)
  console.log('\\n---- 项目列表 ----')
  console.log(txt)
  console.log('----\\n')
  let h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  let size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1100), scale: 2,
    out: path.join(outDir, 'unit-1-projects.png'),
  })
  console.log(`unit-1-projects.png  ${(size / 1024).toFixed(0)} KB`)

  // ---------- 项目详情 ----------
  const hz = me.data.memberships.find((m) => (m.project_name || '').includes('杭州'))
  if (hz) {
    await ws.send('Page.navigate', { url: `${FE}/index.html#/projects/${hz.project_id}` })
    await CDP.sleep(6000)
    txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 1600)`)
    console.log('\\n---- 项目详情 ----')
    console.log(txt)
    console.log('----\\n')
    h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
    size = await CDP.shot(ws, {
      x: 0, y: 0, width: 1560, height: Math.min(h, 1800), scale: 2,
      out: path.join(outDir, 'unit-2-project-detail.png'),
    })
    console.log(`unit-2-project-detail.png  ${(size / 1024).toFixed(0)} KB (高 ${Math.min(h, 1800)})`)
  }

  ws.close()
  process.exit(0)
})().catch((e) => { console.error('FAIL ' + e.message); process.exit(1) })
