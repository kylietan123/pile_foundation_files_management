/**
 * 渲染汇报图：数据库结构与权限设计。
 *
 * 把 HTML 按 data-sec 分区分别截成 2× PNG，便于直接贴进 PPT。
 *
 * 用法：node scripts/render_report.js <cdpPort> <htmlPath> <outDir>
 */
const path = require('path')
const fs = require('fs')
const CDP = require('./cdp')

;(async () => {
  const cdpPort = Number(process.argv[2])
  const htmlPath = process.argv[3]
  const outDir = process.argv[4]

  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })

  const ws = await CDP.openPage(cdpPort, htmlPath, 2200)

  // 页面总览：宽度与各分区的纵向范围
  const info = await CDP.evalJS(
    ws,
    `(function(){
      var page = document.querySelector('.page');
      var head = document.querySelector('.doc-h');
      var note = document.querySelector('.doc-note');
      var secs = Array.from(document.querySelectorAll('section[data-sec]'));
      var topOfFirst = secs.length ? secs[0].getBoundingClientRect().top + window.scrollY : 0;
      var body = {
        pageWidth: Math.ceil(page.getBoundingClientRect().width),
        pagePadTop: 34,
        headerBottom: Math.ceil(note.getBoundingClientRect().bottom + window.scrollY),
        sections: secs.map(function(s){
          var r = s.getBoundingClientRect();
          return {
            name: s.getAttribute('data-sec'),
            top: Math.floor(r.top + window.scrollY) - 14,
            bottom: Math.ceil(r.bottom + window.scrollY) + 10
          };
        }),
        totalHeight: Math.ceil(document.documentElement.scrollHeight)
      };
      return JSON.stringify(body);
    })()`,
  )

  const meta = JSON.parse(info)
  console.log('页面宽:', meta.pageWidth, ' 总高:', meta.totalHeight)
  for (const s of meta.sections) {
    console.log(`  分区 ${s.name}: y ${s.top} → ${s.bottom}  (高 ${s.bottom - s.top})`)
  }

  const W = meta.pageWidth + 4   // 留一点边，避免右侧裁掉

  // ① 封面：标题 + 说明 + 数据库结构的前半（枢纽 + 域卡片上半）
  const coverH = Math.min(meta.sections[0].bottom, meta.headerBottom + 470)
  let size = await CDP.shot(ws, {
    x: 0, y: 0, width: W, height: coverH, scale: 2,
    out: path.join(outDir, 'db-1-总览.png'),
  })
  console.log(`\ndb-1-总览.png          ${(size / 1024).toFixed(0)} KB   ${W}×${coverH}`)

  // ② 数据库结构剩下的部分（域卡片下半）
  if (coverH < meta.sections[0].bottom) {
    const restTop = coverH
    const restH = meta.sections[0].bottom - restTop
    size = await CDP.shot(ws, {
      x: 0, y: restTop, width: W, height: restH, scale: 2,
      out: path.join(outDir, 'db-2-业务域明细.png'),
    })
    console.log(`db-2-业务域明细.png     ${(size / 1024).toFixed(0)} KB   ${W}×${restH}`)
  }

  // ③ 权限设计：推导链 + 三层 + 五要素 + 单位责任矩阵。太高，拆成两段
  const p = meta.sections.find((s) => s.name === 'perm')
  if (p) {
    const h = p.bottom - p.top
    // 前段：权限推导链 + 三层校验 + 成员关系五要素
    const splitAt = p.top + Math.min(760, Math.round(h * 0.46))
    let s1 = await CDP.shot(ws, {
      x: 0, y: p.top, width: W, height: splitAt - p.top, scale: 2,
      out: path.join(outDir, 'perm-1-推导链与三层.png'),
    })
    console.log(`perm-1-推导链与三层.png   ${(s1 / 1024).toFixed(0)} KB   ${W}×${splitAt - p.top}`)

    let s2 = await CDP.shot(ws, {
      x: 0, y: splitAt, width: W, height: p.bottom - splitAt, scale: 2,
      out: path.join(outDir, 'perm-2-单位责任矩阵.png'),
    })
    console.log(`perm-2-单位责任矩阵.png   ${(s2 / 1024).toFixed(0)} KB   ${W}×${p.bottom - splitAt}`)
  }

  // ④ 两条核心机制 + 流转轨迹 + 密级
  const r = meta.sections.find((s) => s.name === 'rules')
  if (r) {
    size = await CDP.shot(ws, {
      x: 0, y: r.top, width: W, height: r.bottom - r.top, scale: 2,
      out: path.join(outDir, 'rules-1-核心机制.png'),
    })
    console.log(`rules-1-核心机制.png    ${(size / 1024).toFixed(0)} KB   ${W}×${r.bottom - r.top}`)
  }

  ws.close()
  process.exit(0)
})().catch((e) => {
  console.error('FAIL ' + e.message)
  process.exit(1)
})
