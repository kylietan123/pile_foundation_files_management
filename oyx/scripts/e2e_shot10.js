/**
 * 我的工作（工作台）页截图。
 * 用法：node scripts/e2e_shot10.js <cdpPort> <outDir>
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

function upload(token, docId, summary) {
  const boundary = '----probe' + Date.now()
  const body = Buffer.concat([
    Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n`),
    Buffer.from('workbench demo content'),
    Buffer.from(`\r\n--${boundary}\r\nContent-Disposition: form-data; name="change_summary"\r\n\r\n${summary}\r\n--${boundary}--\r\n`),
  ])
  return new Promise((resolve) => {
    const r = http.request({
      host: '127.0.0.1', port: 8000, path: `/api/v1/documents/${docId}/versions`, method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': `multipart/form-data; boundary=${boundary}`, 'Content-Length': body.length },
    }, (res) => { let s = ''; res.on('data', (d) => (s += d)); res.on('end', () => { try { resolve(JSON.parse(s)) } catch (e) { resolve({}) } }) })
    r.on('error', () => resolve({}))
    r.write(body); r.end()
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
  const sh = me.data.memberships.find((m) => (m.project_name || '').includes('上海'))
  console.log('项目:', hz.project_name, '/', sh ? sh.project_name : '无上海')

  // 造两个"等我签认"（杭州 + 上海），演示跨项目聚合
  for (const [proj, no] of [[hz, 'WB-DEMO-01'], [sh, 'WB-DEMO-02']]) {
    if (!proj) continue
    const doc = await req('POST', '/api/v1/documents', access_token, {
      project_id: proj.project_id, stage_code: 'DESIGN',
      title: `待我签认的图（${proj.project_name.slice(0, 4)}）`,
      doc_no: no, discipline: '结构', secret_level: 'INTERNAL',
    })
    if (doc.code !== 0) { console.log('建文档失败', no); continue }
    const up = await upload(access_token, doc.data.id, '工作台演示')
    if (up.code !== 0) { console.log('上传失败', no); continue }
    const sub = await req('POST', `/api/v1/versions/${up.data.id}/submit`, access_token, {})
    console.log('造待办:', no, sub.code === 0 ? '成功' : JSON.stringify(sub).slice(0, 80))
  }

  // 造一个"被退回"：提交后让监理退回
  const doc2 = await req('POST', '/api/v1/documents', access_token, {
    project_id: hz.project_id, stage_code: 'DESIGN', title: '被退回的图（演示）',
    doc_no: 'WB-RET-01', discipline: '结构', secret_level: 'INTERNAL',
  })
  if (doc2.code === 0) {
    const up2 = await upload(access_token, doc2.data.id, '会被退回')
    if (up2.code === 0) {
      const vid = up2.data.id
      await req('POST', `/api/v1/versions/${vid}/submit`, access_token, {})
      // 设计单位确认 → 推进到复核
      await req('POST', `/api/v1/versions/${vid}/decide`, access_token,
        { action: 'APPROVE', comment: '主办确认' })
      // 监理退回
      const wl = await req('POST', '/api/v1/auth/login', null, { username: 'wangwu', password: 'Tjad@2026' })
      const r = await req('POST', `/api/v1/versions/${vid}/decide`, wl.data.access_token,
        { action: 'RETURN', comment: '承台配筋需补充抗浮验算依据' })
      console.log('造被退回:', r.code === 0 ? '成功' : JSON.stringify(r).slice(0, 100))
    }
  }

  const ws = await CDP.openPage(cdpPort, 'about:blank', 500)
  await ws.send('Page.navigate', { url: FE + '/index.html' })
  await CDP.sleep(2500)
  await CDP.evalJS(ws, `
    localStorage.setItem('pile_lcm_access_token', ${JSON.stringify(access_token)});
    localStorage.setItem('pile_lcm_refresh_token', ${JSON.stringify(refresh_token)});
    'ok'`)

  await ws.send('Page.navigate', { url: `${FE}/index.html#/my-work` })
  await CDP.sleep(7000)

  let txt = await CDP.evalJS(ws, `document.body.innerText.slice(0, 1400)`)
  console.log('\\n---- 我的工作 ----')
  console.log(txt)
  console.log('----\\n')

  let h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  let size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1100), scale: 2,
    out: path.join(outDir, 'wb-1-等我签认.png'),
  })
  console.log(`wb-1-等我签认.png  ${(size / 1024).toFixed(0)} KB`)

  // 切到"被退回"tab
  const clicked = await CDP.evalJS(ws, `(function(){
    var tabs = document.querySelectorAll('.el-tabs__item');
    for (var i = 0; i < tabs.length; i++) {
      if (tabs[i].innerText.indexOf('被退回') >= 0) { tabs[i].click(); return 'clicked'; }
    }
    return 'not-found';
  })()`)
  console.log('切到被退回:', clicked)
  await CDP.sleep(2500)
  h = await CDP.evalJS(ws, `Math.max(document.documentElement.scrollHeight, 900)`)
  size = await CDP.shot(ws, {
    x: 0, y: 0, width: 1560, height: Math.min(h, 1000), scale: 2,
    out: path.join(outDir, 'wb-2-被退回.png'),
  })
  console.log(`wb-2-被退回.png  ${(size / 1024).toFixed(0)} KB`)

  ws.close()
  process.exit(0)
})().catch((e) => { console.error('FAIL ' + e.message); process.exit(1) })
