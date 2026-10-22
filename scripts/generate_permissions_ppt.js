const path = require('node:path');
const PptxGenJS = require('/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/pptxgenjs');

const pptx = new PptxGenJS();
const W = 13.333;
const H = 7.5;
const FONT = 'Arial Unicode MS';
const FONT_LATIN = 'Aptos';

const C = {
  navy: '0D2E3A',
  navy2: '123D4B',
  ink: '17313B',
  body: '455E68',
  muted: '71858D',
  line: 'DDE7E8',
  paper: 'F4F7F7',
  white: 'FFFFFF',
  teal: '0E8F8B',
  teal2: '25B6AB',
  mint: 'D8F1ED',
  blue: '3E7FCB',
  blueSoft: 'DDEAF8',
  amber: 'D99A2B',
  amberSoft: 'F8EBCB',
  red: 'C75B5B',
  redSoft: 'F6DDDD',
  graySoft: 'EAF0F1',
  slate: '5F737B',
};

pptx.layout = 'LAYOUT_WIDE';
pptx.author = '桩基工程全过程管理平台';
pptx.company = 'TJAD';
pptx.subject = '总体权限管理';
pptx.title = '桩基工程全过程管理平台 · 权限管理总体介绍';
pptx.lang = 'zh-CN';
pptx.theme = {
  headFontFace: FONT,
  bodyFontFace: FONT,
  lang: 'zh-CN',
};

const TOTAL = 12;

function tx(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x, y, w, h,
    fontFace: opts.fontFace || FONT,
    fontSize: opts.fontSize || 13,
    color: opts.color || C.ink,
    bold: opts.bold || false,
    italic: opts.italic || false,
    margin: opts.margin === undefined ? 0 : opts.margin,
    align: opts.align || 'left',
    valign: opts.valign || 'mid',
    breakLine: false,
    fit: opts.fit || 'shrink',
    charSpacing: opts.charSpacing || 0,
    paraSpaceAfterPt: opts.paraSpaceAfterPt || 0,
    lineSpacingMultiple: opts.lineSpacingMultiple || 1,
  });
}

function shape(slide, type, x, y, w, h, opts = {}) {
  slide.addShape(type, {
    x, y, w, h,
    fill: opts.fill || { color: C.white, transparency: 0 },
    line: opts.line || { color: C.line, width: 1, transparency: 0 },
    radius: opts.radius,
    rotate: opts.rotate,
    shadow: opts.shadow || undefined,
  });
}

function rect(slide, x, y, w, h, color, opts = {}) {
  return shape(slide, pptx.ShapeType.rect, x, y, w, h, {
    fill: { color, transparency: opts.transparency || 0 },
    line: opts.line || { color, transparency: 100 },
    rotate: opts.rotate,
  });
}

function round(slide, x, y, w, h, fill, line = C.line, opts = {}) {
  return shape(slide, pptx.ShapeType.roundRect, x, y, w, h, {
    fill: { color: fill, transparency: opts.transparency || 0 },
    line: { color: line, width: opts.lineWidth || 1, transparency: opts.lineTransparency || 0 },
    radius: opts.radius,
    rotate: opts.rotate,
  });
}

function circle(slide, x, y, d, fill, line = fill) {
  return shape(slide, pptx.ShapeType.ellipse, x, y, d, d, {
    fill: { color: fill },
    line: { color: line, width: 1 },
  });
}

function line(slide, x1, y1, x2, y2, color = C.line, width = 1, dash = 'solid') {
  slide.addShape(pptx.ShapeType.line, {
    x: x1, y: y1, w: x2 - x1, h: y2 - y1,
    line: { color, width, dash, beginArrowType: 'none', endArrowType: 'none' },
  });
}

function addBadge(slide, text, x, y, w, fill, color = C.ink, opts = {}) {
  round(slide, x, y, w, opts.h || 0.34, fill, opts.line || fill, { radius: 0.16, lineWidth: 1 });
  tx(slide, text, x + 0.04, y, w - 0.08, opts.h || 0.34, {
    fontSize: opts.fontSize || 9.5,
    color,
    bold: opts.bold === undefined ? true : opts.bold,
    align: 'center',
  });
}

function addActionPills(slide, labels, x, y, maxW, color = C.teal) {
  let px = x;
  let py = y;
  const gap = 0.08;
  for (const label of labels) {
    const w = Math.max(0.55, 0.26 + label.length * 0.16);
    if (px + w > x + maxW) {
      px = x;
      py += 0.43;
    }
    addBadge(slide, label, px, py, w, color, C.white, { h: 0.31, fontSize: 8.7 });
    px += w + gap;
  }
  return py + 0.31;
}

function base(slide, num, section, title, subtitle = '') {
  slide.background = { color: C.paper };
  rect(slide, 0, 0, W, 0.1, C.navy);
  rect(slide, 0.58, 0.62, 0.06, 0.6, C.teal);
  tx(slide, section.toUpperCase(), 0.78, 0.52, 6.6, 0.26, {
    fontSize: 8.5, color: C.teal, bold: true, charSpacing: 1.4,
  });
  tx(slide, title, 0.76, 0.76, 10.6, 0.46, {
    fontSize: 24, color: C.navy, bold: true,
  });
  if (subtitle) {
    tx(slide, subtitle, 0.77, 1.23, 11.4, 0.3, {
      fontSize: 11.5, color: C.muted,
    });
  }
  tx(slide, String(num).padStart(2, '0'), 12.12, 0.48, 0.45, 0.26, {
    fontSize: 9.5, color: C.muted, bold: true, align: 'right', fontFace: FONT_LATIN,
  });
  tx(slide, '桩基工程全过程管理平台  /  权限管理', 0.77, 7.08, 7.5, 0.2, {
    fontSize: 8, color: C.muted,
  });
  tx(slide, `${String(num).padStart(2, '0')} / ${TOTAL}`, 11.72, 7.08, 0.85, 0.2, {
    fontSize: 8, color: C.muted, align: 'right', fontFace: FONT_LATIN,
  });
}

function kicker(slide, text, x, y, w, color = C.teal) {
  circle(slide, x, y + 0.055, 0.1, color);
  tx(slide, text, x + 0.2, y, w - 0.2, 0.24, {
    fontSize: 9.5, color, bold: true,
  });
}

// ---------------------------------------------------------------------------
// 01 Cover
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  s.background = { color: C.navy };
  rect(s, 0, 0, 0.17, H, C.teal2);
  rect(s, 0.17, 0, 0.06, H, C.teal);

  // Matrix motif
  const motifX = 8.55;
  const motifY = 1.15;
  const cell = 0.42;
  const fills = [C.navy2, C.navy2, C.teal, C.navy2, C.teal2, C.navy2, C.navy2, C.blue];
  for (let r = 0; r < 7; r += 1) {
    for (let c = 0; c < 9; c += 1) {
      const idx = (r * 3 + c * 5) % fills.length;
      rect(s, motifX + c * (cell + 0.08), motifY + r * (cell + 0.08), cell, cell,
        fills[idx], { transparency: idx <= 2 ? 32 : 0, line: { color: 'FFFFFF', transparency: 86 } });
    }
  }
  round(s, 9.1, 4.55, 3.35, 0.9, C.navy2, '325563', { lineWidth: 1 });
  tx(s, '7 阶段  ×  10 类单位', 9.36, 4.72, 2.8, 0.24, {
    fontSize: 12, color: C.mint, bold: true, align: 'center',
  });
  tx(s, '责任驱动权限 · 项目内闭环', 9.36, 5.02, 2.8, 0.2, {
    fontSize: 8.5, color: 'C9E1E4', align: 'center',
  });

  tx(s, '桩基工程全过程管理平台', 0.88, 1.05, 6.6, 0.3, {
    fontSize: 11.5, color: 'B9D8DB', bold: true, charSpacing: 1.2,
  });
  tx(s, '权限管理', 0.85, 1.62, 7.6, 0.85, {
    fontSize: 46, color: C.white, bold: true,
  });
  tx(s, '总体方案', 0.85, 2.42, 7.6, 0.85, {
    fontSize: 46, color: C.teal2, bold: true,
  });
  rect(s, 0.89, 3.55, 1.1, 0.055, C.teal2);
  tx(s, '以“参与单位 × 阶段 × 责任等级”为核心的工程协同权限体系', 0.88, 3.9, 7.4, 0.5, {
    fontSize: 18, color: 'DDE9EA', bold: true,
  });
  tx(s, '权限不是一张静态菜单，而是《管理流程》责任矩阵在系统中的实时映射。', 0.9, 4.52, 7.1, 0.58, {
    fontSize: 13, color: 'AFC8CD', lineSpacingMultiple: 1.25,
  });

  const kpis = [
    ['7', '项目阶段'],
    ['10', '参建单位'],
    ['4', '责任等级'],
    ['8', '权限动作'],
  ];
  kpis.forEach(([n, l], i) => {
    const x = 0.9 + i * 1.86;
    tx(s, n, x, 5.56, 0.65, 0.45, { fontSize: 24, color: C.white, bold: true, fontFace: FONT_LATIN });
    tx(s, l, x + 0.66, 5.63, 0.92, 0.23, { fontSize: 9.5, color: 'AFC8CD' });
    if (i < 3) line(s, x + 1.63, 5.56, x + 1.63, 6.02, '4B6570', 1);
  });
  tx(s, '2026.10  ·  系统方案汇报', 0.9, 6.63, 4.0, 0.25, {
    fontSize: 9, color: '8EABB1', charSpacing: 0.8,
  });

  s.addNotes('开场：这份材料介绍平台的总体权限管理。核心不是罗列角色，而是说明权限如何从工程责任矩阵推导出来，并在项目、阶段和具体动作三个层面落地。');
}

// ---------------------------------------------------------------------------
// 02 Executive summary
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 2, 'EXECUTIVE SUMMARY', '一页看懂权限管理', '用一套责任规则，统一“谁能看、谁能做、谁负责、如何追溯”。');

  round(s, 0.76, 1.72, 11.82, 0.86, C.navy, C.navy, { radius: 0.16 });
  tx(s, '核心命题', 1.02, 1.93, 1.0, 0.22, { fontSize: 9.5, color: C.teal2, bold: true });
  tx(s, '权限必须跟着工程责任走，而不是跟着组织架构或前端菜单走。', 2.02, 1.86, 10.0, 0.36, {
    fontSize: 18, color: C.white, bold: true,
  });

  const goals = [
    ['01', '看得见', '项目成员、阶段范围与敏感等级共同决定数据可见性。', C.teal],
    ['02', '管得住', '主办、相关、参与、审查四级责任，直接映射到允许动作。', C.blue],
    ['03', '追得清', '操作人、单位、阶段、对象和结果形成可审计的证据链。', C.amber],
    ['04', '可扩展', '责任划分只改矩阵一处，权限随阶段自动更新。', C.red],
  ];
  goals.forEach(([n, head, desc, color], i) => {
    const y = 2.92 + i * 0.88;
    circle(s, 0.83, y + 0.13, 0.54, color);
    tx(s, n, 0.83, y + 0.13, 0.54, 0.54, {
      fontSize: 9, color: C.white, bold: true, align: 'center', fontFace: FONT_LATIN,
    });
    tx(s, head, 1.58, y + 0.08, 1.35, 0.25, { fontSize: 13, color: C.navy, bold: true });
    tx(s, desc, 2.94, y + 0.05, 4.95, 0.38, { fontSize: 10.5, color: C.body });
  });

  const stats = [
    ['7', '阶段', '前期调研到运维监测', C.teal, C.mint],
    ['10', '类参建单位', '建设、勘察、设计、施工、监理…', C.blue, C.blueSoft],
    ['4', '级责任', '主办 / 相关 / 参与 / 审查', C.amber, C.amberSoft],
    ['8', '项动作', '查看、下载、编辑、提交、发布、签认、提意见、导出', C.red, C.redSoft],
  ];
  stats.forEach(([n, label, desc, color, soft], i) => {
    const x = 8.35 + (i % 2) * 2.05;
    const y = 2.88 + Math.floor(i / 2) * 1.73;
    round(s, x, y, 1.85, 1.48, C.white, C.line, { radius: 0.14 });
    rect(s, x, y, 0.08, 1.48, color);
    tx(s, n, x + 0.22, y + 0.17, 0.65, 0.42, { fontSize: 24, color, bold: true, fontFace: FONT_LATIN });
    tx(s, label, x + 0.78, y + 0.19, 0.9, 0.2, { fontSize: 8.5, color: C.body, bold: true });
    tx(s, desc, x + 0.2, y + 0.72, 1.48, 0.5, { fontSize: 8.2, color: C.muted, lineSpacingMultiple: 1.15 });
  });

  tx(s, '结论：权限模型既是业务控制手段，也是工程责任的可视化表达。', 0.79, 6.53, 11.5, 0.28, {
    fontSize: 11, color: C.teal, bold: true,
  });

  s.addNotes('先给结论：权限管理系统要同时解决四个问题——看得见、管得住、追得清、可扩展。平台的答案是用工程责任矩阵作为唯一权限源。');
}

// ---------------------------------------------------------------------------
// 03 Model
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 3, 'PERMISSION MODEL', '总体权限模型', '主体是参与单位；载体是项目成员；规则来自阶段责任矩阵。');

  const cards = [
    {
      n: '01', title: '账号身份', sub: 'AppUser', color: C.blue,
      lines: ['平台内唯一账号', '账号状态可启用 / 禁用', '认证与业务信息分离'],
    },
    {
      n: '02', title: '单位任职', sub: 'UserOrg', color: C.teal,
      lines: ['一个人可任职多个单位', '标记主单位与本单位管理员', '单位是责任与审计主体'],
    },
    {
      n: '03', title: '项目成员', sub: 'ProjectMember', color: C.amber,
      lines: ['以某单位身份加入项目', '项目级数据范围与有效期', '可覆盖阶段范围与责任'],
    },
    {
      n: '04', title: '阶段责任', sub: 'Responsibility Matrix', color: C.red,
      lines: ['7 阶段 × 10 类单位', '阶段内无责任即无权限', '责任等级推导动作集'],
    },
  ];
  cards.forEach((card, i) => {
    const x = 0.72 + i * 3.14;
    round(s, x, 1.86, 2.72, 3.15, C.white, C.line, { radius: 0.16 });
    rect(s, x, 1.86, 2.72, 0.09, card.color);
    circle(s, x + 0.22, 2.13, 0.52, card.color);
    tx(s, card.n, x + 0.22, 2.13, 0.52, 0.52, {
      fontSize: 9.5, color: C.white, bold: true, align: 'center', fontFace: FONT_LATIN,
    });
    tx(s, card.title, x + 0.9, 2.14, 1.55, 0.27, { fontSize: 15, color: C.navy, bold: true });
    tx(s, card.sub, x + 0.9, 2.45, 1.55, 0.2, { fontSize: 8, color: card.color, bold: true, fontFace: FONT_LATIN });
    card.lines.forEach((ln, j) => {
      circle(s, x + 0.27, 2.94 + j * 0.55 + 0.08, 0.07, card.color);
      tx(s, ln, x + 0.46, 2.86 + j * 0.55, 2.02, 0.33, {
        fontSize: 10, color: C.body, lineSpacingMultiple: 1.1,
      });
    });
    if (i < cards.length - 1) {
      shape(s, pptx.ShapeType.triangle, x + 2.79, 3.22, 0.21, 0.27, {
        fill: { color: 'B8C9CD' }, line: { color: 'B8C9CD', transparency: 100 }, rotate: 90,
      });
    }
  });

  round(s, 0.76, 5.35, 11.82, 1.23, C.navy, C.navy, { radius: 0.16 });
  tx(s, '一次权限判定', 1.0, 5.57, 1.15, 0.24, { fontSize: 9.5, color: C.teal2, bold: true });
  tx(s, '项目范围', 2.24, 5.49, 1.3, 0.35, { fontSize: 17, color: C.white, bold: true });
  tx(s, '×', 3.5, 5.46, 0.35, 0.38, { fontSize: 20, color: C.teal2, bold: true, align: 'center' });
  tx(s, '阶段范围', 3.93, 5.49, 1.3, 0.35, { fontSize: 17, color: C.white, bold: true });
  tx(s, '×', 5.2, 5.46, 0.35, 0.38, { fontSize: 20, color: C.teal2, bold: true, align: 'center' });
  tx(s, '责任动作', 5.64, 5.49, 1.3, 0.35, { fontSize: 17, color: C.white, bold: true });
  tx(s, '任一维度不满足，请求即被拒绝。', 7.42, 5.55, 4.7, 0.28, {
    fontSize: 10.5, color: 'C6D9DC',
  });

  s.addNotes('模型分四层：账号是身份，任职关系说明用户属于哪个单位，项目成员把单位身份带入某个项目，责任矩阵再决定这个单位在该阶段能做什么。最终判定是项目范围、阶段范围和责任动作的交集。');
}

// ---------------------------------------------------------------------------
// 04 Responsibility matrix
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 4, 'RESPONSIBILITY MATRIX', '7 个阶段 × 10 类参建单位', '矩阵中有等级，系统中才有角色；没有列出的单位，在该阶段不可见。');

  const units = ['建设', '勘察', '设计试桩', '设计', '总包', '分包', '监理', '验收试桩', '检测监测', '政府审查'];
  const rows = [
    ['前期调研', ['P', '', '', '', '', '', '', '', '', 'R']],
    ['勘察', ['A', 'P', '', 'A', '', '', 'A', '', '', 'A']],
    ['设计试桩', ['A', 'A', 'P', 'R', 'A', '', 'A', 'A', 'A', 'R']],
    ['设计', ['A', 'A', 'A', 'P', 'A', 'A', 'R', 'A', 'A', 'R']],
    ['施工', ['A', 'A', '', 'A', 'P', 'R', 'R', '', 'A', 'R']],
    ['验收试桩', ['A', 'A', '', 'R', 'A', 'R', 'A', 'P', 'A', '']],
    ['运维监测', ['R', '', '', 'A', '', '', '', '', 'P', '']],
  ];
  const statusMap = {
    P: ['主办', '0B807B', C.white],
    R: ['相关', 'D7E7F7', '244E7A'],
    A: ['参与', 'E6EDEF', C.body],
    '': ['—', 'F8FAFA', 'B4C1C5'],
  };

  const x0 = 0.62;
  const y0 = 1.76;
  const stageW = 1.48;
  const unitW = 0.965;
  const headH = 0.62;
  const rowH = 0.47;

  rect(s, x0, y0, stageW + unitW * units.length, headH + rowH * rows.length, C.white, { line: C.line });
  rect(s, x0, y0, stageW, headH, C.navy);
  tx(s, '阶段 / 单位', x0 + 0.1, y0, stageW - 0.2, headH, {
    fontSize: 8.8, color: C.white, bold: true, align: 'center',
  });
  units.forEach((u, i) => {
    rect(s, x0 + stageW + i * unitW, y0, unitW, headH, C.navy2);
    tx(s, u, x0 + stageW + i * unitW + 0.02, y0 + 0.03, unitW - 0.04, headH - 0.06, {
      fontSize: u.length > 3 ? 7.4 : 8.6, color: C.white, bold: true, align: 'center', lineSpacingMultiple: 0.95,
    });
  });

  rows.forEach(([stage, vals], r) => {
    const yy = y0 + headH + r * rowH;
    rect(s, x0, yy, stageW, rowH, r % 2 === 0 ? 'F1F5F5' : C.white, { line: C.line, line: { color: 'E8EEEF', width: 0.7 } });
    tx(s, stage, x0 + 0.12, yy, stageW - 0.2, rowH, {
      fontSize: 9.2, color: C.navy, bold: true,
    });
    vals.forEach((v, i) => {
      const [label, fill, color] = statusMap[v];
      rect(s, x0 + stageW + i * unitW, yy, unitW, rowH, fill, { line: { color: C.white, width: 2 } });
      tx(s, label, x0 + stageW + i * unitW, yy, unitW, rowH, {
        fontSize: v ? 8.3 : 9, color, bold: !!v, align: 'center',
      });
    });
  });

  const legend = [
    ['主办', '0B807B', C.white, '可编辑、提交、发布、签认'],
    ['相关', 'D7E7F7', '244E7A', '可签认、提意见'],
    ['参与', 'E6EDEF', C.body, '只读、可下载'],
    ['审查', 'F8EBCB', '8B6217', '专项场景下可提意见'],
  ];
  legend.forEach(([label, fill, color, desc], i) => {
    const x = 0.7 + i * 3.02;
    round(s, x, 6.05, 0.5, 0.27, fill, fill, { radius: 0.13 });
    tx(s, label, x, 6.05, 0.5, 0.27, { fontSize: 7.5, color, bold: true, align: 'center' });
    tx(s, desc, x + 0.61, 6.04, 2.18, 0.27, { fontSize: 8.3, color: C.muted });
  });
  tx(s, '读法：先定位阶段，再定位单位；责任等级决定该阶段内的动作边界。', 0.72, 6.52, 11.6, 0.25, {
    fontSize: 9.2, color: C.teal, bold: true,
  });

  s.addNotes('这张矩阵是整套权限的核心。每个阶段只有明确列出的单位能够进入；每个单位的责任等级决定它是主办、相关、参与还是专项审查。权限随责任矩阵自动变化，不需要为七个阶段重复维护七套角色。');
}

// ---------------------------------------------------------------------------
// 05 Responsibility -> actions
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 5, 'ACTION DERIVATION', '责任等级决定动作权限', '权限动作由责任等级自动推导，避免“矩阵一套、代码另一套”。');

  const rows = [
    {
      title: '主办', tag: 'PRIMARY', desc: '对本阶段成果负主要责任', color: C.teal,
      actions: ['查看', '下载', '编辑', '提交', '发布', '签认'],
    },
    {
      title: '相关', tag: 'RELATED', desc: '参与复核与协同确认', color: C.blue,
      actions: ['查看', '下载', '签认', '提意见'],
    },
    {
      title: '参与', tag: 'PARTICIPANT', desc: '知情、查阅与下载', color: C.slate,
      actions: ['查看', '下载'],
    },
    {
      title: '审查', tag: 'VERIFIER', desc: '专项审查场景下提出意见', color: C.amber,
      actions: ['查看', '下载', '提意见'],
    },
  ];

  rows.forEach((row, i) => {
    const y = 1.78 + i * 1.0;
    round(s, 0.74, y, 8.25, 0.82, C.white, C.line, { radius: 0.13 });
    rect(s, 0.74, y, 0.09, 0.82, row.color);
    tx(s, row.title, 0.99, y + 0.15, 0.88, 0.28, { fontSize: 15, color: C.navy, bold: true });
    tx(s, row.tag, 0.99, y + 0.48, 1.0, 0.16, { fontSize: 6.8, color: row.color, bold: true, fontFace: FONT_LATIN });
    tx(s, row.desc, 1.93, y + 0.22, 1.72, 0.34, { fontSize: 9.1, color: C.muted, lineSpacingMultiple: 1.05 });
    addActionPills(s, row.actions, 3.73, y + 0.235, 4.92, row.color);
  });

  round(s, 9.35, 1.78, 3.2, 4.63, C.navy, C.navy, { radius: 0.16 });
  tx(s, '权限推导链', 9.66, 2.0, 2.55, 0.26, { fontSize: 10, color: C.teal2, bold: true });
  const chain = [
    ['阶段 × 单位', '查《管理流程》矩阵'],
    ['责任等级', '主办 / 相关 / 参与 / 审查'],
    ['动作集合', '由等级自动展开'],
  ];
  chain.forEach(([h, d], i) => {
    const y = 2.55 + i * 1.02;
    round(s, 9.66, y, 2.56, 0.72, i === 1 ? '174B57' : '143D49', '315A65', { radius: 0.1 });
    tx(s, h, 9.85, y + 0.11, 2.18, 0.22, { fontSize: 10.5, color: C.white, bold: true });
    tx(s, d, 9.85, y + 0.39, 2.18, 0.18, { fontSize: 7.7, color: 'AFC8CD' });
    if (i < chain.length - 1) {
      shape(s, pptx.ShapeType.triangle, 10.77, y + 0.76, 0.34, 0.18, {
        fill: { color: C.teal2 }, line: { color: C.teal2, transparency: 100 }, rotate: 180,
      });
    }
  });
  round(s, 9.66, 5.73, 2.56, 0.43, '1A3F48', '315A65', { radius: 0.08 });
  tx(s, '唯一例外：系统管理员可跨项目维护', 9.8, 5.73, 2.28, 0.43, {
    fontSize: 7.2, color: 'C9E1E4', bold: true, align: 'center', lineSpacingMultiple: 1.0,
  });

  tx(s, '设计原则：不单独给“角色”勾选 70+ 个阶段/单位组合，避免出现权限配置与工程责任不一致。', 0.77, 6.53, 11.7, 0.26, {
    fontSize: 9.2, color: C.teal, bold: true,
  });

  s.addNotes('责任等级只有四种，但每种等级对应一组确定的动作。主办单位能编辑、提交、发布；相关单位能复核签认；参与单位只读；审查单位在专项场景中提意见。这样权限配置不需要逐项勾选。');
}

// ---------------------------------------------------------------------------
// 06 Request decision
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 6, 'ENFORCEMENT', '一次请求如何完成判权', '从身份到数据，五个关口依次校验；前端只优化体验，后端才是安全边界。');

  const steps = [
    ['01', '身份认证', '有效账号\nJWT 未过期', C.blue],
    ['02', '项目准入', '存在有效\n项目成员关系', C.teal],
    ['03', '阶段准入', '阶段在可见\n范围内', C.teal2],
    ['04', '动作判定', '责任等级允许\n该动作', C.amber],
    ['05', '数据过滤', '查询条件先行\n只返回可见数据', C.red],
  ];
  steps.forEach(([n, title, desc, color], i) => {
    const x = 0.72 + i * 2.45;
    round(s, x, 1.92, 2.12, 2.32, C.white, C.line, { radius: 0.15 });
    circle(s, x + 0.19, 2.13, 0.49, color);
    tx(s, n, x + 0.19, 2.13, 0.49, 0.49, {
      fontSize: 8.8, color: C.white, bold: true, align: 'center', fontFace: FONT_LATIN,
    });
    tx(s, title, x + 0.79, 2.16, 1.15, 0.28, { fontSize: 12.5, color: C.navy, bold: true });
    tx(s, desc, x + 0.23, 2.86, 1.66, 0.68, { fontSize: 9.1, color: C.body, lineSpacingMultiple: 1.25 });
    if (i < steps.length - 1) {
      shape(s, pptx.ShapeType.triangle, x + 2.15, 2.98, 0.2, 0.24, {
        fill: { color: 'A9BEC2' }, line: { color: 'A9BEC2', transparency: 100 }, rotate: 90,
      });
    }
  });

  round(s, 0.74, 4.56, 5.72, 1.55, C.amberSoft, 'F0D9A7', { radius: 0.15 });
  tx(s, '前端体验层', 1.02, 4.84, 1.4, 0.25, { fontSize: 11, color: '7A581B', bold: true });
  tx(s, '隐藏无权按钮、灰化无权限阶段、提示“为什么不能操作”。', 1.02, 5.16, 4.95, 0.43, {
    fontSize: 10.5, color: '6B542C', lineSpacingMultiple: 1.2,
  });
  tx(s, '目的：减少误操作，不承担安全职责。', 1.02, 5.66, 4.7, 0.22, { fontSize: 8.5, color: '8A713D' });

  round(s, 6.68, 4.56, 5.9, 1.55, C.navy, C.navy, { radius: 0.15 });
  tx(s, '后端安全层', 6.98, 4.84, 1.4, 0.25, { fontSize: 11, color: C.teal2, bold: true });
  tx(s, '每个接口重新构建 Principal，重新校验；项目与阶段过滤进入 SQL。', 6.98, 5.16, 5.1, 0.43, {
    fontSize: 10.5, color: C.white, lineSpacingMultiple: 1.2,
  });
  addBadge(s, '未通过 → 403 / 空列表', 10.45, 5.62, 1.82, C.red, C.white, { h: 0.3, fontSize: 7.8 });

  tx(s, '统一入口：can(action, project, stage)  ·  列表场景：scoped query 先行过滤', 0.78, 6.48, 11.7, 0.26, {
    fontSize: 9.2, color: C.teal, bold: true,
  });

  s.addNotes('对一次请求来说，要依次通过身份、项目、阶段、动作和数据过滤五个关口。尤其要强调：前端隐藏按钮只是体验优化，不能作为安全措施；后端必须在每个接口重新校验，列表查询也必须先过滤权限再取数。');
}

// ---------------------------------------------------------------------------
// 07 Construction example
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 7, 'SCENARIO', '同一施工阶段，不同单位看到不同动作', '项目、阶段、数据底稿相同；差异全部来自责任等级。');

  const cards = [
    {
      org: '总包单位', role: '主办', count: '6', color: C.teal, soft: C.mint,
      note: '本阶段成果的主要责任单位',
      actions: ['查看', '下载', '编辑', '提交', '发布', '签认'],
    },
    {
      org: '分包单位', role: '相关', count: '4', color: C.blue, soft: C.blueSoft,
      note: '参与协同并完成复核确认',
      actions: ['查看', '下载', '签认', '提意见'],
    },
    {
      org: '监理单位', role: '相关', count: '4', color: C.blue, soft: C.blueSoft,
      note: '参与复核并提出监理意见',
      actions: ['查看', '下载', '签认', '提意见'],
    },
    {
      org: '建设单位', role: '参与', count: '2', color: C.slate, soft: C.graySoft,
      note: '知情、查阅与下载留档',
      actions: ['查看', '下载'],
    },
  ];

  cards.forEach((card, i) => {
    const x = 0.72 + i * 3.12;
    round(s, x, 1.88, 2.75, 3.85, C.white, C.line, { radius: 0.16 });
    rect(s, x, 1.88, 2.75, 0.1, card.color);
    tx(s, card.org, x + 0.24, 2.17, 1.42, 0.28, { fontSize: 15, color: C.navy, bold: true });
    addBadge(s, card.role, x + 1.87, 2.14, 0.63, card.soft, card.color, { h: 0.3, fontSize: 8.2 });
    tx(s, card.count, x + 0.24, 2.78, 0.6, 0.56, { fontSize: 29, color: card.color, bold: true, fontFace: FONT_LATIN });
    tx(s, '项允许动作', x + 0.84, 2.94, 1.2, 0.22, { fontSize: 9, color: C.muted });
    tx(s, card.note, x + 0.24, 3.53, 2.22, 0.42, { fontSize: 9.5, color: C.body, lineSpacingMultiple: 1.15 });
    card.actions.forEach((a, j) => {
      const col = j % 2;
      const row = Math.floor(j / 2);
      addBadge(s, a, x + 0.24 + col * 1.12, 4.22 + row * 0.42, 0.98, card.soft, card.color, { h: 0.3, fontSize: 8.5 });
    });
  });

  round(s, 0.75, 6.05, 11.82, 0.62, C.navy, C.navy, { radius: 0.12 });
  tx(s, '同一份施工资料', 1.0, 6.22, 1.25, 0.2, { fontSize: 8.5, color: 'AFC8CD', bold: true });
  tx(s, '总包可发起与发布  →  分包、监理可复核签认  →  建设方可查阅留档', 2.35, 6.16, 7.95, 0.3, {
    fontSize: 12.2, color: C.white, bold: true,
  });

  s.addNotes('以施工阶段为例：总包是主办单位，可以编辑、提交、发布；分包和监理是相关单位，可以查看、下载、复核签认和提意见；建设单位是参与单位，只能查看和下载。大家在同一个项目、同一个阶段看到同一份底稿，但操作权限不同。');
}

// ---------------------------------------------------------------------------
// 08 Two-level sign-off
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 8, 'WORKFLOW', '两级签认，把流程责任落到单位', '主办单位确认 + 相关单位复核；发布责任始终由主办单位承担。');

  const laneX = 1.93;
  const colW = 2.06;
  const cols = ['上传草稿', '主办确认', '相关复核', '主办发布', '后续修订'];
  cols.forEach((c, i) => {
    const x = laneX + i * (colW + 0.08);
    round(s, x, 1.78, colW, 0.5, C.navy, C.navy, { radius: 0.08 });
    tx(s, c, x, 1.78, colW, 0.5, { fontSize: 9.7, color: C.white, bold: true, align: 'center' });
  });

  const lanes = [
    { label: '主办单位', y: 2.52, color: C.teal, soft: C.mint },
    { label: '相关单位', y: 3.57, color: C.blue, soft: C.blueSoft },
    { label: '审查单位', y: 4.62, color: C.amber, soft: C.amberSoft },
    { label: '文件状态', y: 5.67, color: C.slate, soft: C.graySoft },
  ];
  lanes.forEach((lane) => {
    round(s, 0.72, lane.y, 1.06, 0.72, lane.soft, lane.soft, { radius: 0.1 });
    tx(s, lane.label, 0.72, lane.y, 1.06, 0.72, { fontSize: 9.6, color: lane.color, bold: true, align: 'center', lineSpacingMultiple: 1.0 });
    for (let i = 0; i < 5; i += 1) {
      rect(s, laneX + i * (colW + 0.08), lane.y, colW, 0.72, i % 2 === 0 ? 'F3F6F6' : 'EDF2F3', {
        line: { color: 'E3EAEB', width: 0.7 },
      });
    }
  });

  function block(rowIndex, colIndex, text, color, soft, sub = '') {
    const y = lanes[rowIndex].y + 0.08;
    const x = laneX + colIndex * (colW + 0.08) + 0.08;
    round(s, x, y, colW - 0.16, 0.56, soft, soft, { radius: 0.08 });
    tx(s, text, x + 0.06, y + (sub ? 0.06 : 0.05), colW - 0.28, sub ? 0.22 : 0.38, {
      fontSize: 9.2, color, bold: true, align: 'center',
    });
    if (sub) tx(s, sub, x + 0.06, y + 0.29, colW - 0.28, 0.16, { fontSize: 7, color, align: 'center' });
  }

  block(0, 0, '创建 / 上传', C.teal, C.mint, 'EDIT');
  block(0, 1, '主办确认', C.teal, C.mint, 'CONFIRM');
  block(0, 3, '发布', C.teal, C.mint, 'PUBLISH');
  block(0, 4, '发起修订', C.teal, C.mint, 'NEW VERSION');
  block(1, 2, '复核 / 签认 / 提意见', C.blue, C.blueSoft, 'CONFIRM · COMMENT');
  block(2, 2, '提出审查意见', C.amber, C.amberSoft, 'COMMENT');
  block(3, 0, '草稿', C.slate, C.graySoft, 'DRAFT');
  block(3, 1, '确认中', C.slate, C.graySoft, 'CHECKING');
  block(3, 2, '复核中', C.slate, C.graySoft, 'REVIEWING');
  block(3, 3, '已发布', C.slate, C.graySoft, 'PUBLISHED');
  block(3, 4, '新版本', C.slate, C.graySoft, 'IMMUTABLE');

  // Arrows between main flow cells
  for (let i = 0; i < 4; i += 1) {
    if (i === 2) continue;
    shape(s, pptx.ShapeType.triangle, laneX + (i + 1) * (colW + 0.08) - 0.015, lanes[0].y + 0.25, 0.16, 0.2, {
      fill: { color: '9EB3B7' }, line: { color: '9EB3B7', transparency: 100 }, rotate: 90,
    });
  }
  line(s, laneX + 3 * (colW + 0.08) + colW / 2, lanes[0].y + 0.65, laneX + 3 * (colW + 0.08) + colW / 2, lanes[1].y + 0.08, C.teal, 1.2, 'dash');
  line(s, laneX + 2 * (colW + 0.08) + colW / 2, lanes[1].y + 0.65, laneX + 3 * (colW + 0.08) + colW / 2, lanes[0].y + 0.65, C.blue, 1.2, 'dash');

  round(s, 0.76, 6.45, 11.8, 0.31, C.mint, C.mint, { radius: 0.1 });
  tx(s, '核心约束：签认资格由任务指派决定；发布的唯一责任主体是阶段主办单位；已发布版本不可覆盖，只能新建版本。', 0.96, 6.45, 11.4, 0.31, {
    fontSize: 8.7, color: C.teal, bold: true,
  });

  s.addNotes('权限不仅控制增删改查，也控制流程。平台采用两级签认：主办单位先确认，相关单位再复核，最后由主办单位发布。政府审查单位按专项任务提意见，不替代主办单位的签发责任。发布后的版本不可覆盖，只能新建版本。');
}

// ---------------------------------------------------------------------------
// 09 Administration chain
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 9, 'GOVERNANCE', '管理授权链：谁能给谁授权', '平台管理、单位管理、阶段管理分层设置，避免管理员权限无限外溢。');

  const tiers = [
    {
      level: '平台级', title: '系统管理员', color: C.red, soft: C.redSoft,
      lines: ['创建账号、启停账号、重置密码', '设置单位管理员、跨项目查看与维护', '唯一超级管理员角色'],
    },
    {
      level: '项目级', title: '建设单位管理员', color: C.amber, soft: C.amberSoft,
      lines: ['审核项目是否进入进行中', '添加其他参与单位人员', '配置可见阶段与阶段责任'],
    },
    {
      level: '阶段级', title: '阶段负责人', color: C.teal, soft: C.mint,
      lines: ['只能添加本单位员工', '只能分配自己负责的阶段', '不能跨单位、跨阶段授权'],
    },
    {
      level: '业务级', title: '项目成员', color: C.blue, soft: C.blueSoft,
      lines: ['在授权项目与阶段内操作', '动作由责任等级自动决定', '全部关键操作留痕'],
    },
  ];
  tiers.forEach((tier, i) => {
    const y = 1.72 + i * 1.18;
    round(s, 0.77, y, 7.65, 0.98, C.white, C.line, { radius: 0.13 });
    rect(s, 0.77, y, 0.09, 0.98, tier.color);
    round(s, 1.02, y + 0.21, 0.79, 0.31, tier.soft, tier.soft, { radius: 0.08 });
    tx(s, tier.level, 1.02, y + 0.21, 0.79, 0.31, { fontSize: 7.6, color: tier.color, bold: true, align: 'center' });
    tx(s, tier.title, 1.99, y + 0.15, 1.75, 0.28, { fontSize: 13.5, color: C.navy, bold: true });
    tier.lines.forEach((ln, j) => {
      circle(s, 3.85, y + 0.19 + j * 0.23, 0.055, tier.color);
      tx(s, ln, 3.99, y + 0.13 + j * 0.23, 4.2, 0.2, { fontSize: 7.8, color: C.body });
    });
    if (i < tiers.length - 1) {
      line(s, 1.41, y + 0.98, 1.41, y + 1.18, 'AFC0C4', 1.2, 'dash');
    }
  });

  round(s, 8.75, 1.72, 3.8, 5.05, C.navy, C.navy, { radius: 0.16 });
  tx(s, '三条授权边界', 9.08, 2.02, 3.1, 0.26, { fontSize: 11, color: C.teal2, bold: true });
  const boundaries = [
    ['不跨项目', '成员关系按项目建立，A 项目权限不会放大 B 项目。'],
    ['不跨单位', '阶段负责人只能管理本单位员工。'],
    ['不跨阶段', '阶段负责人只能分配自己负责的阶段。'],
  ];
  boundaries.forEach(([h, d], i) => {
    const y = 2.55 + i * 1.18;
    circle(s, 9.08, y, 0.34, C.teal2);
    tx(s, String(i + 1), 9.08, y, 0.34, 0.34, { fontSize: 8, color: C.navy, bold: true, align: 'center', fontFace: FONT_LATIN });
    tx(s, h, 9.58, y - 0.02, 1.2, 0.22, { fontSize: 10.5, color: C.white, bold: true });
    tx(s, d, 9.58, y + 0.27, 2.48, 0.55, { fontSize: 8.2, color: 'B9D0D5', lineSpacingMultiple: 1.15 });
  });
  round(s, 9.08, 6.0, 3.05, 0.45, '193F48', '315A65', { radius: 0.08 });
  tx(s, '普通账号访问 /admin：后端返回 403', 9.2, 6.0, 2.8, 0.45, {
    fontSize: 7.4, color: 'C9E1E4', bold: true, align: 'center',
  });

  s.addNotes('管理系统不是只有一个超级管理员。平台管理员负责账号与平台配置；建设单位管理员负责项目审核和参与单位配置；阶段负责人只能管理本单位、自己负责的阶段；普通成员在业务范围内操作。权限按作用域逐层收窄。');
}

// ---------------------------------------------------------------------------
// 10 Standard + exceptions
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 10, 'CONFIGURATION', '标准规则优先，项目例外可控', '默认使用全局责任矩阵；只有个别项目偏离标准分工时，才启用项目级覆盖。');

  round(s, 0.75, 1.78, 5.82, 3.7, C.white, C.line, { radius: 0.16 });
  rect(s, 0.75, 1.78, 5.82, 0.1, C.teal);
  addBadge(s, '默认路径', 1.02, 2.05, 0.77, C.mint, C.teal, { h: 0.3, fontSize: 8 });
  tx(s, '标准项目：完全由矩阵推导', 1.02, 2.5, 4.9, 0.32, { fontSize: 16, color: C.navy, bold: true });
  const defaults = [
    ['阶段范围', '取该单位在矩阵中出现的阶段'],
    ['责任等级', '取 responsibility_of(stage, unit)'],
    ['动作集合', '由责任等级自动展开'],
    ['配置成本', '不新增 7 × 10 条独立配置'],
  ];
  defaults.forEach(([k, v], i) => {
    const y = 3.03 + i * 0.55;
    tx(s, k, 1.02, y, 0.86, 0.22, { fontSize: 9.2, color: C.teal, bold: true });
    tx(s, v, 1.99, y, 4.1, 0.22, { fontSize: 9.2, color: C.body });
    line(s, 1.02, y + 0.33, 5.98, y + 0.33, 'E7EDEE', 0.8);
  });

  round(s, 6.77, 1.78, 5.82, 3.7, C.white, C.line, { radius: 0.16 });
  rect(s, 6.77, 1.78, 5.82, 0.1, C.amber);
  addBadge(s, '例外路径', 7.04, 2.05, 0.77, C.amberSoft, '8B6217', { h: 0.3, fontSize: 8 });
  tx(s, '特殊项目：项目成员级覆盖', 7.04, 2.5, 4.95, 0.32, { fontSize: 16, color: C.navy, bold: true });
  const exceptions = [
    ['stage_scope', '限制或扩大可见阶段范围'],
    ['responsibility_override', '例：CONSTRUCTION=PRIMARY'],
    ['作用范围', '仅当前项目成员关系，不改全局矩阵'],
    ['可回收', '撤销、失效或恢复标准配置'],
  ];
  exceptions.forEach(([k, v], i) => {
    const y = 3.03 + i * 0.55;
    tx(s, k, 7.04, y, 1.6, 0.22, { fontSize: 8.1, color: '8B6217', bold: true, fontFace: FONT_LATIN });
    tx(s, v, 8.72, y, 3.5, 0.22, { fontSize: 8.9, color: C.body });
    line(s, 7.04, y + 0.33, 12.02, y + 0.33, 'E7EDEE', 0.8);
  });

  const chips = [
    ['多人多身份', '遍历全部成员关系取并集'],
    ['按项目隔离', 'A 项目身份不会放大 B 项目'],
    ['时间有效', '支持生效、失效与撤销'],
  ];
  chips.forEach(([h, d], i) => {
    const x = 0.76 + i * 4.0;
    round(s, x, 5.83, 3.77, 0.72, i === 1 ? C.navy : C.graySoft, i === 1 ? C.navy : C.line, { radius: 0.11 });
    tx(s, h, x + 0.22, 5.95, 1.2, 0.2, { fontSize: 9.4, color: i === 1 ? C.teal2 : C.teal, bold: true });
    tx(s, d, x + 1.35, 5.96, 2.2, 0.2, { fontSize: 7.8, color: i === 1 ? 'C9E1E4' : C.body });
  });
  tx(s, '治理原则：标准规则是默认值；例外必须明确、局部、可解释、可回收。', 0.78, 6.7, 11.5, 0.24, {
    fontSize: 9.2, color: C.teal, bold: true,
  });

  s.addNotes('绝大多数项目应直接走矩阵，不需要额外配置。只有在项目责任划分确实与标准矩阵不同的时候，才在项目成员上做阶段范围或责任等级覆盖。覆盖只作用于当前项目，不污染全局，也可以失效或撤销。');
}

// ---------------------------------------------------------------------------
// 11 Security and audit
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  base(s, 11, 'SECURITY & AUDIT', '安全控制与审计留痕', '权限管理的最后一公里，是让每一次访问和操作都可验证、可追溯。');

  const cards = [
    {
      title: '身份安全', tag: 'IDENTITY', color: C.blue, soft: C.blueSoft,
      lines: ['PBKDF2-HMAC-SHA256 · 260,000 次', 'JWT 有效期校验 · 账号启停', '姓名、工号与单位进入操作主体'],
    },
    {
      title: '访问安全', tag: 'ACCESS', color: C.teal, soft: C.mint,
      lines: ['每个接口独立重新判权', '项目与阶段过滤进入 SQL', '越权返回 403 或无结果'],
    },
    {
      title: '版本安全', tag: 'VERSION', color: C.amber, soft: C.amberSoft,
      lines: ['文件内容 SHA-256 寻址', '原始文件不可变，修改即新版本', '已发布版本不覆盖、不回退'],
    },
    {
      title: '行为审计', tag: 'AUDIT', color: C.red, soft: C.redSoft,
      lines: ['记录操作人、单位、项目与阶段', '覆盖创建、提交、审批、发布、下载', '日志用于追责、核验与问题复盘'],
    },
  ];
  cards.forEach((card, i) => {
    const x = 0.74 + (i % 2) * 5.97;
    const y = 1.78 + Math.floor(i / 2) * 2.18;
    round(s, x, y, 5.72, 1.9, C.white, C.line, { radius: 0.15 });
    rect(s, x, y, 0.09, 1.9, card.color);
    circle(s, x + 0.29, y + 0.27, 0.48, card.color);
    tx(s, card.tag.slice(0, 1), x + 0.29, y + 0.27, 0.48, 0.48, {
      fontSize: 11, color: C.white, bold: true, align: 'center', fontFace: FONT_LATIN,
    });
    tx(s, card.title, x + 0.93, y + 0.23, 2.1, 0.27, { fontSize: 14, color: C.navy, bold: true });
    tx(s, card.tag, x + 0.93, y + 0.54, 2.2, 0.17, { fontSize: 6.8, color: card.color, bold: true, fontFace: FONT_LATIN });
    card.lines.forEach((ln, j) => {
      circle(s, x + 0.31, y + 1.04 + j * 0.24, 0.055, card.color);
      tx(s, ln, x + 0.45, y + 0.98 + j * 0.24, 4.88, 0.2, { fontSize: 8.4, color: C.body });
    });
  });

  round(s, 0.75, 6.24, 11.84, 0.52, C.navy, C.navy, { radius: 0.1 });
  tx(s, '审计不是“多记一条日志”，而是让权限决定、责任归属和文件版本形成完整证据链。', 1.0, 6.24, 11.35, 0.52, {
    fontSize: 11, color: C.white, bold: true, align: 'center',
  });

  s.addNotes('安全控制分四层：身份、访问、版本和审计。尤其要说明两点：第一，权限校验在后端重复执行；第二，文件内容用 SHA-256 寻址，修改必须产生新版本；第三，关键业务动作会记录操作人、单位、阶段和对象，形成证据链。');
}

// ---------------------------------------------------------------------------
// 12 Closing
// ---------------------------------------------------------------------------
{
  const s = pptx.addSlide();
  s.background = { color: C.navy };
  rect(s, 0, 0, W, 0.1, C.teal2);
  rect(s, 0.85, 1.02, 0.08, 0.66, C.teal2);
  tx(s, 'SUMMARY', 1.1, 0.92, 2.0, 0.24, { fontSize: 9, color: C.teal2, bold: true, charSpacing: 1.2 });
  tx(s, '让权限成为业务规则的投影', 1.07, 1.22, 10.6, 0.55, { fontSize: 30, color: C.white, bold: true });
  tx(s, '而不是额外的配置负担。', 1.07, 1.78, 5.3, 0.45, { fontSize: 23, color: 'AFC8CD' });

  const pillars = [
    ['01', '一个矩阵', '《管理流程》责任矩阵是唯一权限源。', C.teal2],
    ['02', '一条链路', '项目 → 阶段 → 责任等级 → 动作。', C.blue],
    ['03', '一套留痕', '人、单位、阶段、版本与审计全部可追溯。', C.amber],
  ];
  pillars.forEach(([n, h, d, color], i) => {
    const x = 1.05 + i * 3.82;
    round(s, x, 3.05, 3.42, 1.78, '143D49', '315A65', { radius: 0.14 });
    tx(s, n, x + 0.25, 3.28, 0.45, 0.24, { fontSize: 9, color, bold: true, fontFace: FONT_LATIN });
    tx(s, h, x + 0.25, 3.62, 2.9, 0.3, { fontSize: 17, color: C.white, bold: true });
    tx(s, d, x + 0.25, 4.08, 2.85, 0.43, { fontSize: 9.5, color: 'AFC8CD', lineSpacingMultiple: 1.2 });
  });

  rect(s, 1.06, 5.42, 11.25, 0.02, '3C5963');
  tx(s, '最终目标', 1.08, 5.8, 0.9, 0.24, { fontSize: 8.5, color: C.teal2, bold: true });
  tx(s, '每一份工程文件，都能找到它的责任单位、责任阶段和责任人。', 2.02, 5.67, 10.2, 0.5, {
    fontSize: 18.5, color: C.white, bold: true,
  });
  tx(s, '桩基工程全过程管理平台  ·  权限管理总体介绍', 1.08, 6.68, 6.0, 0.22, {
    fontSize: 8.5, color: '8EABB1',
  });

  s.addNotes('收尾回到一句话：权限管理最终要保证每一份工程文件都能找到责任单位、责任阶段和责任人。平台用一个矩阵作为唯一权限源，用一条链路完成判定，用一套留痕完成追溯。');
}

const out = path.resolve('/Users/kylie/Desktop/桩基工程全过程管理/桩基工程全过程管理平台_权限管理总体介绍.pptx');
pptx.writeFile({ fileName: out })
  .then(() => console.log(`PPT generated: ${out}`))
  .catch((err) => {
    console.error(err);
    process.exitCode = 1;
  });
