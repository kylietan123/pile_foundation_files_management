/**
 * 文件台账与追溯页截图。
 * 用法：node scripts/e2e_shot9.js <cdpPort> <outDir>
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

  // 造一份"卡在签认中"的文件，让台账有在途可看
  const doc = await req('POST', '/api/v1/documents', access_token, {
    project_id: hz.project_id, stage_code: 'DESIGN', title: '桩基施工图（第二版修订）',
    doc_no: 'JG-SG-02', discipline: '结构', secret_level: 'INTERNAL',
  })
  if (doc.code === 0) {
    const did = doc.data.id
    // 直接走表单上传比较麻烦，用 multipart 请求
    const boundary = '----probe' + Date.now()
    const body = Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
      Buffer.from('probe content'),
      Buffer.from(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="change_summary"\r\n\r\n台账演示版本\r\n--${boundary}--\r\n`),
    ])
    const up = await new Promise((resolve) => {
      const r = http.request({
        host: '127.0.0.1', port: 8000, path: `/api/v1/documents/${did}/versions`, method: 'POST',
        headers: { Authorization: `Bearer ${access_token}`, 'Content-Type': `multipart/form-data; boundary=${boundary}`, 'Content-Length': body.length },
      }, (res) => { let s = ''; res.on('data', (d) => (s += d)); res.on('end', () => { try { resolve(JSON.parse(s)) } catch (e) { resolve({}) } }) })
      r.on('error', () => resolve({}))
      r.write(body); r.end()
    })
    if (up.code === 0) {
      const vid = up.data.id
      const sub = await req('POST', `/api/v1/versions/${vid}/submit`, access_token, {})
      console.log('造在途文件:', doc.data.doc_no, '提交:', sub.code === 0 ? '成功' : JSON.stringify(sub).slice(0, 80))
    }
  }

  const ws = await CDP.openPage(cdpPort, 'about:blank', 500)
  await ws.send('Page.navigate', { url: FE + '/index.html' })
  await CDP.sleep(2500)
  await CDP.evalJS(ws, `
    localStorage.setItem('pile_lcm_access_token', ${JSON.stringify(access_token)});
    localStorage.setItem('pile_lcm_refresh_token', ${JSON.stringify(refresh_token)});
    'ok'`)

  await ws.send('Page.navigate', { url: `${FE}/index.html#/projects/${hz.project_id}/ledger` })
  await CDP.sleep(7000)

  const txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 1800)`)
  console.log('\\n---- 台账页 ----')
  console.log(txt)
  console.log('----\\n')

  const h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  const size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 2000), scale: 2,
    out: path.join(outDir, 'ledger-1-台账.png'),
  })
  console.log(`ledger-1-台账.png  ${(size / 1024).toFixed(0)} KB (高 ${Math.min(h, 2000)})`)

  // 打开详情抽屉
  const opened = await CDP.evalJS(ws, `(function(){
    var rows = document.querySelectorAll('.el-table__row');
    if (!rows.length) return 'no-row';
    rows[0].click();
    return 'clicked';
  })()`)
  console.log('打开详情:', opened)
  await CDP.sleep(3000)
  const size2 = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: 1000, scale: 2,
    out: path.join(outDir, 'ledger-2-追溯.png'),
  })
  console.log(`ledger-2-追溯.png  ${(size2 / 1024).toFixed(0)} KB`)

  ws.close()
  process.exit(0)
})().catch((e) => { console.error('FAIL ' + e.message); process.exit(1) })
