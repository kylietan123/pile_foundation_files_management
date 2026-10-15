/**
 * 设计输入页（输入文件库 + 参数溯源）截图。
 * 用法：node scripts/e2e_shot11.js <cdpPort> <outDir>
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
  const me = await req('GET', '/api/v1/auth/me', access_token)
  const hz = me.data.memberships.find((m) => (m.project_name || '').includes('杭州'))
  console.log('项目:', hz.project_name)

  const ws = await CDP.openPage(cdpPort, 'about:blank', 500)
  await ws.send('Page.navigate', { url: FE + '/index.html' })
  await CDP.sleep(2500)
  await CDP.evalJS(ws, `
    localStorage.setItem('pile_lcm_access_token', ${JSON.stringify(access_token)});
    localStorage.setItem('pile_lcm_refresh_token', ${JSON.stringify(refresh_token)});
    'ok'`)

  await ws.send('Page.navigate', { url: `${FE}/index.html#/projects/${hz.project_id}/design-inputs` })
  await CDP.sleep(7000)

  let txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 1200)`)
  console.log('\\n---- 输入文件库 ----')
  console.log(txt)
  console.log('----\\n')

  let h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  let size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1100), scale: 2,
    out: path.join(outDir, 'input-1-文件库.png'),
  })
  console.log(`input-1-文件库.png  ${(size / 1024).toFixed(0)} KB`)

  // 切到参数溯源
  const clicked = await CDP.evalJS(ws, `(function(){
    var tabs = document.querySelectorAll('.el-tabs__item');
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].innerText.indexOf('参数溯源') >= 0) { tabs[i].click(); return 'clicked'; }
    }
    return 'not-found';
  })()`)
  console.log('切到参数溯源:', clicked)
  await CDP.sleep(4000)
  txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 600)`)
  console.log('\\n---- 参数溯源（前 600 字）----')
  console.log(txt)
  h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1200), scale: 2,
    out: path.join(outDir, 'input-2-参数溯源.png'),
  })
  console.log(`input-2-参数溯源.png  ${(size / 1024).toFixed(0)} KB`)

  ws.close()
  process.exit(0)
})().catch((e) => { console.error('FAIL ' + e.message); process.exit(1) })
