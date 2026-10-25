import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

process.env.RUNTIME_NODE_MODULES = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const OUT = "/Users/kylie/Desktop/桩基工程全过程管理/.codex-build/pile-construction-deck/artifacts";
const WORKSPACE_DIR = "/Users/kylie/Desktop/桩基工程全过程管理";
const SKILL_DIR = "/Users/kylie/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations";
const RUNTIME_PYTHON = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const FINAL_PPTX = "/Users/kylie/Desktop/桩基工程全过程管理/output/桩基施工阶段功能与流程设计_简单版.pptx";
const FONT = "Hiragino Sans GB";
const C = {
  navy: "#102A43",
  navy2: "#173F5F",
  red: "#B4232C",
  redSoft: "#FBE9EB",
  blue: "#2563A6",
  blueSoft: "#EAF2FA",
  teal: "#0F8B8D",
  tealSoft: "#E7F5F5",
  ink: "#1C2733",
  gray: "#5F6B7A",
  muted: "#8491A2",
  light: "#F4F7FA",
  border: "#DCE4EC",
  white: "#FFFFFF",
  amber: "#B7791F",
  amberSoft: "#FFF4DD",
};

const slideW = 1280;
const slideH = 720;

function addText(slide, text, pos, style = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    position: pos,
    fill: "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = text;
  shape.text.style = {
    typeface: FONT,
    color: C.ink,
    fontSize: 16,
    verticalAlignment: "top",
    wrap: "square",
    ...style,
  };
  return shape;
}

function addCard(slide, pos, opts = {}) {
  return slide.shapes.add({
    geometry: "roundRect",
    position: pos,
    fill: opts.fill ?? C.light,
    line: {
      style: "solid",
      fill: opts.line ?? C.border,
      width: opts.lineWidth ?? 1,
    },
    borderRadius: "rounded-xl",
  });
}

function addLine(slide, pos, color = C.border, width = 1) {
  return slide.shapes.add({
    geometry: "rect",
    position: pos,
    fill: color,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

function addArrow(slide, left, top, width = 24, height = 18, color = C.red, direction = "right") {
  return slide.shapes.add({
    geometry: direction === "right" ? "rightArrow" : "downArrow",
    position: { left, top, width, height },
    fill: color,
    line: { style: "solid", fill: "none", width: 0 },
  });
}

function addChip(slide, text, left, top, width, opts = {}) {
  const fill = opts.fill ?? C.white;
  const color = opts.color ?? C.navy2;
  const card = slide.shapes.add({
    geometry: "roundRect",
    position: { left, top, width, height: opts.height ?? 30 },
    fill,
    line: { style: "solid", fill: opts.line ?? C.border, width: 1 },
    borderRadius: "rounded-full",
  });
  card.text = text;
  card.text.style = {
    typeface: FONT,
    fontSize: opts.fontSize ?? 13,
    bold: opts.bold ?? false,
    color,
    alignment: "center",
    verticalAlignment: "middle",
    insets: { left: 10, right: 10, top: 0, bottom: 0 },
  };
  return card;
}

function addHeader(slide, title, subtitle, index) {
  slide.background.fill = C.white;
  addLine(slide, { left: 64, top: 42, width: 38, height: 5 }, C.red);
  addText(slide, title, { left: 64, top: 62, width: 1120, height: 52 }, {
    fontSize: 31,
    bold: true,
    color: C.navy,
    lineSpacing: 1.05,
  });
  if (subtitle) {
    addText(slide, subtitle, { left: 64, top: 116, width: 1120, height: 30 }, {
      fontSize: 15,
      color: C.gray,
    });
  }
  addText(slide, "桩基施工阶段 · 功能与流程设计", { left: 64, top: 686, width: 360, height: 20 }, {
    fontSize: 10,
    color: C.muted,
  });
  addText(slide, String(index).padStart(2, "0"), { left: 1180, top: 684, width: 36, height: 20 }, {
    fontSize: 10,
    color: C.muted,
    alignment: "right",
  });
}

function addBulletBlock(slide, items, left, top, width, height, opts = {}) {
  const paragraphs = items.map((item) => ({
    bulletCharacter: "•",
    marginLeft: 18,
    indent: -10,
    spaceAfter: opts.spaceAfter ?? 7,
    runs: [item],
  }));
  return addText(slide, paragraphs, { left, top, width, height }, {
    fontSize: opts.fontSize ?? 15,
    color: opts.color ?? C.ink,
    lineSpacing: opts.lineSpacing ?? 1.15,
  });
}

function styleTableHeader(table, cols) {
  for (let c = 0; c < cols; c += 1) {
    const cell = table.getCell(0, c);
    cell.fill = C.navy;
    cell.text.style = {
      typeface: FONT,
      fontSize: 14,
      bold: true,
      color: C.white,
      verticalAlignment: "middle",
      insets: { left: 10, right: 8, top: 5, bottom: 5 },
    };
  }
}

function styleTableBody(table, rows, cols, opts = {}) {
  for (let r = 1; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const cell = table.getCell(r, c);
      cell.fill = r % 2 === 0 ? C.light : C.white;
      cell.text.style = {
        typeface: FONT,
        fontSize: opts.fontSize ?? 13.5,
        color: C.ink,
        bold: c === 0,
        verticalAlignment: "middle",
        insets: { left: 10, right: 8, top: 5, bottom: 5 },
      };
    }
  }
}

function addMetric(slide, value, label, left, top, width) {
  addText(slide, value, { left, top, width, height: 42 }, {
    fontSize: 28,
    bold: true,
    color: C.red,
    alignment: "center",
  });
  addText(slide, label, { left, top: top + 42, width, height: 24 }, {
    fontSize: 12.5,
    color: C.gray,
    alignment: "center",
  });
}

const presentation = Presentation.create({ slideSize: { width: slideW, height: slideH } });

// -------------------- Slide 1: Cover --------------------
{
  const slide = presentation.slides.add();
  slide.background.fill = C.navy;
  addLine(slide, { left: 0, top: 0, width: 16, height: 720 }, C.red);
  addText(slide, "桩基工程全过程管理平台", { left: 72, top: 74, width: 520, height: 26 }, {
    fontSize: 14,
    bold: true,
    color: "#AFC5D9",
  });
  addText(slide, "桩基施工阶段\n功能与流程设计", { left: 72, top: 176, width: 720, height: 156 }, {
    fontSize: 50,
    bold: true,
    color: C.white,
    lineSpacing: 1.1,
  });
  addText(slide, "从开工准备到资料移交，建立一桩一档、验收闭环和资料包闭环", {
    left: 76,
    top: 352,
    width: 670,
    height: 54,
  }, {
    fontSize: 18,
    color: "#D9E5F0",
    lineSpacing: 1.25,
  });

  const chips = ["32 类施工资料", "4 类责任单位", "9 个功能模块", "8 个流程节点"];
  let x = 76;
  for (const chip of chips) {
    addChip(slide, chip, x, 448, chip.length > 7 ? 150 : 128, {
      fill: "rgba(255,255,255,0.08)",
      line: "#42627E",
      color: C.white,
      fontSize: 13,
    });
    x += chip.length > 7 ? 164 : 142;
  }

  // Abstract pile foundation diagram
  addLine(slide, { left: 900, top: 184, width: 286, height: 26 }, "#7F99B1");
  for (let i = 0; i < 8; i += 1) {
    const px = 918 + i * 32;
    addLine(slide, { left: px, top: 202, width: 8, height: 278 }, i % 2 === 0 ? "#D9E5F0" : "#AFC5D9");
    slide.shapes.add({
      geometry: "ellipse",
      position: { left: px - 1, top: 474, width: 10, height: 10 },
      fill: C.red,
      line: { style: "solid", fill: "none", width: 0 },
    });
  }
  addText(slide, "PILE FOUNDATION", { left: 906, top: 520, width: 260, height: 24 }, {
    fontSize: 11,
    bold: true,
    color: "#8FA8BD",
    alignment: "center",
  });

  addText(slide, "依据：《桩基工程文档管理智能体工作计划》《桩基工程全过程管理文档清单》", {
    left: 76,
    top: 646,
    width: 760,
    height: 24,
  }, {
    fontSize: 11,
    color: "#9FB3C6",
  });
  slide.speakerNotes.text =
    "封面。设计依据：桩基工程文档管理智能体工作计划.pdf；桩基工程全过程管理文档清单.xlsx。施工阶段共32类文档。";
}

// -------------------- Slide 2: Positioning --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "施工阶段应围绕“桩、资料、验收”形成闭环", "施工阶段既是现场执行过程，也是资料形成和移交过程。", 2);

  const cards = [
    ["01", "施工准备", "方案审批、开工条件、测量交接", C.blueSoft, C.blue],
    ["02", "桩位施工", "一桩一档、过程记录、进度统计", C.light, C.navy2],
    ["03", "质量闭环", "报验、隐蔽验收、检测监测", C.tealSoft, C.teal],
    ["04", "资料移交", "32 类资料包、阶段完成门槛", C.redSoft, C.red],
  ];
  cards.forEach(([num, title, desc, fill, accent], i) => {
    const left = 64 + i * 286;
    addCard(slide, { left, top: 178, width: 262, height: 182 }, { fill });
    addText(slide, num, { left: left + 20, top: 196, width: 50, height: 24 }, {
      fontSize: 13,
      bold: true,
      color: accent,
    });
    addText(slide, title, { left: left + 20, top: 226, width: 220, height: 34 }, {
      fontSize: 23,
      bold: true,
      color: C.navy,
    });
    addText(slide, desc, { left: left + 20, top: 274, width: 218, height: 58 }, {
      fontSize: 14,
      color: C.gray,
      lineSpacing: 1.25,
    });
  });

  addLine(slide, { left: 64, top: 404, width: 1152, height: 1 }, C.border);
  addMetric(slide, "32", "类施工资料", 80, 438, 200);
  addMetric(slide, "4", "类责任单位", 320, 438, 200);
  addMetric(slide, "1 : 1", "一桩一档", 560, 438, 200);
  addMetric(slide, "6", "类完成门槛", 800, 438, 200);

  addCard(slide, { left: 1012, top: 432, width: 204, height: 105 }, { fill: C.amberSoft, line: "#F0D39A" });
  addText(slide, "待确认", { left: 1030, top: 446, width: 80, height: 22 }, {
    fontSize: 12,
    bold: true,
    color: C.amber,
  });
  addText(slide, "5.1 六项与勘察阶段\n条目重复，建议核对", { left: 1030, top: 474, width: 166, height: 48 }, {
    fontSize: 13,
    color: C.ink,
    lineSpacing: 1.25,
  });

  addText(slide, "建议采用“阶段责任 + 文档责任”两层权限，避免分包、监理、检测无法上传自己负责的资料。", {
    left: 80,
    top: 584,
    width: 1100,
    height: 40,
  }, {
    fontSize: 16,
    bold: true,
    color: C.navy2,
    alignment: "center",
  });

  slide.speakerNotes.text =
    "依据：桩基工程全过程管理文档清单.xlsx。施工阶段共32类文档，其中总包6类、分包8类、监理9类、检测监测9类。清单5.1.1-5.1.6与地质勘察阶段条目高度重复，建议确认为模板复制还是施工阶段特有要求。";
}

// -------------------- Slide 3: Roles & permissions --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "四类单位共同参与，但职责必须分开", "阶段责任决定能否进入；文档责任决定谁编制、谁审核、谁签认。", 3);

  const rows = [
    ["角色", "主要职责", "关键控制"],
    ["建设单位", "阶段统筹、重大审批、验收", "开工令、重大方案、阶段移交"],
    ["工程总包", "施工牵头、分包管理、总包复核", "施工组织、进度、资料汇总"],
    ["桩基分包", "施工执行、过程记录、自检", "专项方案、成孔/浇筑/沉桩"],
    ["监理单位", "旁站、见证、报验审核、复查", "旁站记录、检验批、整改复查"],
    ["检测监测", "检测方案、检测报告、监测预警", "静载、低应变、声波、钻芯、高应变"],
    ["设计单位", "技术澄清、设计变更", "异常桩处理、变更影响"],
    ["勘察单位", "地质异常、补孔、持力层确认", "补孔通知、地质确认"],
  ];
  const table = slide.tables.add({
    rows: 8,
    columns: 3,
    left: 64,
    top: 176,
    width: 786,
    height: 432,
    columnWidths: [132, 300, 354],
    values: rows,
  });
  styleTableHeader(table, 3);
  styleTableBody(table, 8, 3, { fontSize: 13.2 });
  table.borders.assign({ style: "solid", fill: C.border, width: 1 });

  addCard(slide, { left: 880, top: 176, width: 336, height: 432 }, { fill: C.light });
  addText(slide, "双层权限模型", { left: 904, top: 198, width: 280, height: 30 }, {
    fontSize: 22,
    bold: true,
    color: C.navy,
  });
  addCard(slide, { left: 904, top: 244, width: 288, height: 96 }, { fill: C.blueSoft, line: "#B8D1E8" });
  addText(slide, "阶段访问", { left: 922, top: 260, width: 120, height: 24 }, {
    fontSize: 15,
    bold: true,
    color: C.blue,
  });
  addText(slide, "按《管理流程》责任矩阵\n决定能否进入施工阶段", { left: 922, top: 288, width: 244, height: 44 }, {
    fontSize: 13,
    color: C.ink,
    lineSpacing: 1.25,
  });
  addText(slide, "↓", { left: 1030, top: 344, width: 32, height: 24 }, {
    fontSize: 22,
    bold: true,
    color: C.red,
    alignment: "center",
  });
  addCard(slide, { left: 904, top: 374, width: 288, height: 116 }, { fill: C.redSoft, line: "#E8BFC3" });
  addText(slide, "文档责任", { left: 922, top: 390, width: 120, height: 24 }, {
    fontSize: 15,
    bold: true,
    color: C.red,
  });
  addText(slide, "编制 / 审核 / 签认 / 只读\n按清单责任单位配置", { left: 922, top: 418, width: 244, height: 44 }, {
    fontSize: 13,
    color: C.ink,
    lineSpacing: 1.25,
  });
  addText(slide, "分包、监理、检测应能上传各自资料", { left: 904, top: 518, width: 286, height: 40 }, {
    fontSize: 14,
    bold: true,
    color: C.navy2,
    alignment: "center",
    lineSpacing: 1.2,
  });

  slide.speakerNotes.text =
    "当前平台阶段矩阵中，总包为施工阶段主办，分包和监理为相关，检测为参与；但清单要求分包、监理、检测分别编制大量资料。因此建议增加文档责任单位、编制单位、审核单位、签认单位字段，不能只用阶段责任等级控制上传权限。";
}

// -------------------- Slide 4: Modules --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "一个施工工作台承载九类核心功能", "从现场记录到资料归档，所有功能围绕“桩”和“资料包”组织。", 4);

  const modules = [
    ["01", "施工总览", "进度、质量、风险、资料齐全率"],
    ["02", "施工准备", "方案审批、开工条件、测量交接"],
    ["03", "桩位台账", "一桩一档、状态、平面图"],
    ["04", "施工记录", "成孔/钢筋笼/浇筑/沉桩/影像"],
    ["05", "报验验收", "自检、总包复核、监理验收"],
    ["06", "检测监测", "检测报告、监测预警、复测"],
    ["07", "问题与变更", "整改闭环、变更影响分析"],
    ["08", "资料包", "5.1-5.4、完整性、移交"],
    ["09", "AI 助手", "分类、抽取、检查、日报"],
  ];
  modules.forEach(([num, title, desc], i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const left = 64 + col * 390;
    const top = 176 + row * 158;
    addCard(slide, { left, top, width: 366, height: 136 }, { fill: row === 1 ? C.white : C.light });
    addText(slide, num, { left: left + 20, top: top + 18, width: 40, height: 22 }, {
      fontSize: 12,
      bold: true,
      color: C.red,
    });
    addText(slide, title, { left: left + 62, top: top + 14, width: 270, height: 30 }, {
      fontSize: 20,
      bold: true,
      color: C.navy,
    });
    addText(slide, desc, { left: left + 22, top: top + 62, width: 320, height: 48 }, {
      fontSize: 14,
      color: C.gray,
      lineSpacing: 1.2,
    });
  });

  slide.speakerNotes.text =
    "功能架构建议：施工总览、施工准备、桩位台账、施工记录、报验验收、检测监测、问题与变更、资料包、AI助手。施工总览应直接展示阶段完成门槛，而不是只展示文档数量。";
}

// -------------------- Slide 5: Main flow --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "从开工到移交，施工阶段分为八个节点", "流程按“准备—施工—验收—移交”推进，每个节点都有明确输出。", 5);

  const steps = [
    ["1", "施工准备", "方案 / 人员 / 机械 / 材料"],
    ["2", "开工条件", "测量 / 试桩 / 报审"],
    ["3", "开工审批", "监理核查 / 开工令"],
    ["4", "试桩首件", "工艺验证 / 首件验收"],
    ["5", "批量施工", "单桩记录 / 进度"],
    ["6", "报验验收", "隐蔽 / 检验批"],
    ["7", "检测监测", "报告 / 预警 / 整改"],
    ["8", "完工移交", "分部验收 / 资料包"],
  ];
  steps.forEach(([num, title, desc], i) => {
    const row = i < 4 ? 0 : 1;
    const col = i % 4;
    const left = 64 + col * 286;
    const top = 166 + row * 176;
    addCard(slide, { left, top, width: 252, height: 106 }, { fill: row === 0 ? C.blueSoft : C.light });
    addText(slide, num, { left: left + 16, top: top + 14, width: 32, height: 24 }, {
      fontSize: 13,
      bold: true,
      color: row === 0 ? C.blue : C.red,
    });
    addText(slide, title, { left: left + 48, top: top + 12, width: 180, height: 28 }, {
      fontSize: 18,
      bold: true,
      color: C.navy,
    });
    addText(slide, desc, { left: left + 18, top: top + 56, width: 214, height: 34 }, {
      fontSize: 13,
      color: C.gray,
      lineSpacing: 1.15,
    });
    if (col < 3) addArrow(slide, left + 258, top + 44, 22, 18, row === 0 ? C.blue : C.teal);
  });
  addArrow(slide, 1138, 286, 20, 44, C.red, "down");

  addCard(slide, { left: 64, top: 536, width: 1152, height: 78 }, { fill: C.redSoft, line: "#E8BFC3" });
  addText(slide, "阶段完成门槛", { left: 88, top: 552, width: 140, height: 24 }, {
    fontSize: 14,
    bold: true,
    color: C.red,
  });
  addText(slide, "资料齐  ·  桩完成  ·  检测闭  ·  问题清  ·  变更闭  ·  签认全", {
    left: 222,
    top: 550,
    width: 960,
    height: 30,
  }, {
    fontSize: 20,
    bold: true,
    color: C.navy,
    alignment: "center",
  });
  addText(slide, "未达到门槛不得进入验收试桩阶段", { left: 824, top: 582, width: 356, height: 20 }, {
    fontSize: 12,
    color: C.gray,
    alignment: "right",
  });

  slide.speakerNotes.text =
    "主流程8个节点：施工准备、开工条件、开工审批、试桩/首件、批量施工、报验验收、检测监测、完工移交。阶段完成门槛由资料、桩完成、检测、问题、变更和签认共同决定。";
}

// -------------------- Slide 6: One pile one file --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "单桩施工记录与验收构成最小质量闭环", "每一根桩都应形成“记录—复核—验收—检测—归档”的完整链条。", 6);

  const steps = ["设计桩位", "施工记录", "分包自检", "总包复核", "监理验收", "检测", "归档"];
  const start = 64;
  const width = 148;
  const gap = 16;
  steps.forEach((s, i) => {
    const left = start + i * (width + gap);
    addCard(slide, { left, top: 170, width, height: 76 }, { fill: i === 0 ? C.blueSoft : i === steps.length - 1 ? C.redSoft : C.light });
    addText(slide, s, { left: left + 10, top: 188, width: width - 20, height: 24 }, {
      fontSize: 15,
      bold: true,
      color: i === 0 ? C.blue : i === steps.length - 1 ? C.red : C.navy,
      alignment: "center",
    });
    addText(slide, String(i + 1).padStart(2, "0"), { left: left + 10, top: 214, width: width - 20, height: 16 }, {
      fontSize: 10,
      color: C.muted,
      alignment: "center",
    });
    if (i < steps.length - 1) addArrow(slide, left + width + 2, 200, 12, 14, C.red);
  });

  addCard(slide, { left: 64, top: 286, width: 590, height: 320 }, { fill: C.light });
  addText(slide, "一桩一档：记录内容", { left: 88, top: 306, width: 300, height: 30 }, {
    fontSize: 21,
    bold: true,
    color: C.navy,
  });
  addBulletBlock(slide, [
    "成孔记录 / 沉桩记录",
    "钢筋笼制作与安装",
    "混凝土浇筑 / 后注浆",
    "接桩、桩头凿除",
    "班组技术交底、施工日志",
    "现场照片 / 视频",
  ], 92, 352, 510, 220, { fontSize: 15, spaceAfter: 9 });
  addText(slide, "记录完成 → 自动更新桩台账状态", { left: 92, top: 556, width: 510, height: 24 }, {
    fontSize: 14,
    bold: true,
    color: C.navy2,
  });

  addCard(slide, { left: 678, top: 286, width: 538, height: 320 }, { fill: C.white });
  addText(slide, "质量控制点", { left: 702, top: 306, width: 260, height: 30 }, {
    fontSize: 21,
    bold: true,
    color: C.navy,
  });
  const controls = [
    ["H", "停工待检点", "未经监理放行不得进入下一道工序"],
    ["W", "见证点", "见证取样、见证送检"],
    ["S", "旁站点", "关键工序监理现场旁站"],
  ];
  controls.forEach(([code, title, desc], i) => {
    const top = 356 + i * 64;
    addChip(slide, code, 704, top, 34, { height: 30, fill: C.redSoft, line: C.red, color: C.red, bold: true, fontSize: 12 });
    addText(slide, title, { left: 750, top: top - 2, width: 150, height: 24 }, {
      fontSize: 15,
      bold: true,
      color: C.navy,
    });
    addText(slide, desc, { left: 750, top: top + 22, width: 420, height: 20 }, {
      fontSize: 12.5,
      color: C.gray,
    });
  });
  addText(slide, "未验收不得进入下一道工序", { left: 702, top: 558, width: 460, height: 26 }, {
    fontSize: 16,
    bold: true,
    color: C.red,
    alignment: "center",
  });

  slide.speakerNotes.text =
    "单桩闭环：设计桩位→施工记录→分包自检→总包复核→监理验收→检测→归档。质量控制点采用H/W/S分类，未验收不得进入下一道工序。";
}

// -------------------- Slide 7: Testing / monitoring / issues / change --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "检测、监测、问题与变更必须互相触发", "不合格报告和监测预警不能停留在文件层面，必须进入闭环。", 7);

  const cols = [
    {
      title: "检测",
      fill: C.blueSoft,
      accent: C.blue,
      items: ["检测方案与资质", "低应变 / 声波 / 钻芯", "静载 / 高应变", "检测报告与复检"],
      flow: "不合格 → 问题单 → 整改 → 复检 → 关闭",
      flowColor: C.red,
    },
    {
      title: "监测",
      fill: C.tealSoft,
      accent: C.teal,
      items: ["沉降 / 位移 / 水位", "监测点与频率", "阈值与预警等级", "日报 / 周报 / 月报"],
      flow: "预警 → 会商 → 处置 → 复测 → 关闭",
      flowColor: C.teal,
    },
    {
      title: "问题与变更",
      fill: C.redSoft,
      accent: C.red,
      items: ["质量问题 / 监测预警", "技术澄清 / 设计变更", "已施工桩影响分析", "成本与工期影响"],
      flow: "未闭环不得进入阶段验收",
      flowColor: C.red,
    },
  ];
  cols.forEach((col, i) => {
    const left = 64 + i * 390;
    addCard(slide, { left, top: 172, width: 366, height: 402 }, { fill: col.fill });
    addText(slide, col.title, { left: left + 22, top: 194, width: 260, height: 32 }, {
      fontSize: 23,
      bold: true,
      color: col.accent,
    });
    addBulletBlock(slide, col.items, left + 22, 244, 320, 170, { fontSize: 14.5, spaceAfter: 9 });
    addCard(slide, { left: left + 20, top: 438, width: 326, height: 94 }, { fill: C.white, line: C.border });
    addText(slide, col.flow, { left: left + 34, top: 456, width: 298, height: 56 }, {
      fontSize: 13.5,
      bold: true,
      color: col.flowColor,
      alignment: "center",
      lineSpacing: 1.25,
    });
  });

  addText(slide, "所有关闭必须有监理确认和审计留痕", { left: 180, top: 614, width: 920, height: 30 }, {
    fontSize: 17,
    bold: true,
    color: C.navy2,
    alignment: "center",
  });

  slide.speakerNotes.text =
    "检测不合格必须自动触发问题单；监测预警必须触发会商、处置和复测；设计变更必须做已施工桩、图纸、成本、工期影响分析。所有关闭必须有监理确认和审计留痕。";
}

// -------------------- Slide 8: Document packages & gate --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "资料包完整性决定施工阶段能否完成", "32 类资料按四类责任单位组织，未齐不得进入验收试桩阶段。", 8);

  const packs = [
    ["5.1", "总包统筹包", "6 类", "施工准备、分包管理、测量交接"],
    ["5.2", "分包执行包", "8 类", "专项方案、施工记录、隐蔽验收"],
    ["5.3", "监理控制包", "9 类", "旁站、见证、报验、检验批"],
    ["5.4", "检测监测包", "9 类", "资质、方案、检测报告、预警"],
  ];
  packs.forEach(([code, title, count, desc], i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const left = 64 + col * 300;
    const top = 174 + row * 154;
    addCard(slide, { left, top, width: 276, height: 132 }, { fill: row === 0 ? C.light : C.white });
    addText(slide, code, { left: left + 18, top: top + 16, width: 60, height: 24 }, {
      fontSize: 13,
      bold: true,
      color: C.red,
    });
    addText(slide, title, { left: left + 18, top: top + 42, width: 220, height: 28 }, {
      fontSize: 19,
      bold: true,
      color: C.navy,
    });
    addText(slide, count, { left: left + 196, top: top + 16, width: 60, height: 24 }, {
      fontSize: 13,
      bold: true,
      color: C.navy2,
      alignment: "right",
    });
    addText(slide, desc, { left: left + 18, top: top + 82, width: 238, height: 36 }, {
      fontSize: 12.5,
      color: C.gray,
      lineSpacing: 1.15,
    });
  });

  addCard(slide, { left: 676, top: 174, width: 540, height: 386 }, { fill: C.redSoft, line: "#E8BFC3" });
  addText(slide, "阶段完成门槛", { left: 704, top: 196, width: 260, height: 30 }, {
    fontSize: 22,
    bold: true,
    color: C.red,
  });
  addBulletBlock(slide, [
    "32 类必填资料均有有效版本",
    "需审批资料全部批准 / 发布",
    "全部桩完成施工记录",
    "检测、监测、问题、变更闭环",
    "竣工图、桩位台账、施工总结齐全",
    "总包、监理、建设单位完成签认",
  ], 708, 242, 474, 260, { fontSize: 14.5, spaceAfter: 9, color: C.ink });
  addText(slide, "资料包未齐 → 不允许提交阶段验收", { left: 704, top: 508, width: 480, height: 28 }, {
    fontSize: 15,
    bold: true,
    color: C.red,
    alignment: "center",
  });

  const statuses = ["未上传", "草稿", "审核中", "已批准", "已发布", "过期", "不适用"];
  let x = 64;
  statuses.forEach((s, i) => {
    const w = i === statuses.length - 1 ? 80 : 92;
    addChip(slide, s, x, 594, w, {
      height: 28,
      fill: i === 4 ? C.tealSoft : i === 5 ? C.amberSoft : C.light,
      line: i === 4 ? C.teal : i === 5 ? "#E8C98D" : C.border,
      color: i === 4 ? C.teal : i === 5 ? C.amber : C.gray,
      fontSize: 11.5,
    });
    x += w + 8;
  });
  addText(slide, "30 类需审批  ·  2 类影像资料", { left: 820, top: 594, width: 396, height: 26 }, {
    fontSize: 12.5,
    color: C.gray,
    alignment: "right",
  });

  slide.speakerNotes.text =
    "资料包按清单5.1-5.4组织：总包6类、分包8类、监理9类、检测监测9类。施工阶段完成必须具备32类资料有效版本、桩完成、检测监测问题变更闭环、竣工资料齐全、总包监理建设签认。清单5.1六项与勘察阶段重复，需业务确认。";
}

// -------------------- Slide 9: Roadmap & AI --------------------
{
  const slide = presentation.slides.add();
  addHeader(slide, "先建基础闭环，再叠加 AI 与移动端", "优先保证现场可用和数据闭环，再逐步增加智能检查与报告生成。", 9);

  addCard(slide, { left: 64, top: 172, width: 552, height: 230 }, { fill: C.light });
  addText(slide, "页面入口", { left: 88, top: 192, width: 180, height: 30 }, {
    fontSize: 21,
    bold: true,
    color: C.navy,
  });
  const entries = ["施工总览", "桩位台账", "施工记录", "报验验收", "检测监测", "资料包", "AI 助手"];
  let ex = 88;
  let ey = 242;
  entries.forEach((e, i) => {
    const w = i === 0 ? 96 : 110;
    if (ex + w > 590) {
      ex = 88;
      ey += 46;
    }
    addChip(slide, e, ex, ey, w, { height: 32, fill: C.white, fontSize: 13 });
    ex += w + 10;
  });

  addCard(slide, { left: 646, top: 172, width: 570, height: 230 }, { fill: C.blueSoft });
  addText(slide, "AI 能力", { left: 670, top: 192, width: 180, height: 30 }, {
    fontSize: 21,
    bold: true,
    color: C.blue,
  });
  addBulletBlock(slide, [
    "施工资料自动分类",
    "桩号、日期、方量、检测结论抽取",
    "资料完整性与一致性检查",
    "施工日报 / 周报自动生成",
    "带版本引用的施工知识问答",
  ], 674, 240, 500, 140, { fontSize: 14, spaceAfter: 6 });

  addCard(slide, { left: 64, top: 432, width: 1152, height: 156 }, { fill: C.white });
  addText(slide, "12 周实施节奏", { left: 88, top: 450, width: 240, height: 28 }, {
    fontSize: 18,
    bold: true,
    color: C.navy,
  });
  const phases = [
    ["第 5-6 周", "基础闭环", C.blue],
    ["第 7 周", "验收 / 问题", C.teal],
    ["第 8 周", "检测 + AI", C.navy2],
    ["第 9-10 周", "AI 检查 / 报告", C.red],
    ["第 11-12 周", "移动端 / 优化 / 验收", C.amber],
  ];
  let px = 88;
  phases.forEach(([wk, label, color], i) => {
    addChip(slide, wk, px, 496, 150, { height: 28, fill: C.light, line: C.border, color, bold: true, fontSize: 12 });
    addText(slide, label, { left: px, top: 532, width: 150, height: 36 }, {
      fontSize: 12.5,
      color: C.ink,
      alignment: "center",
      lineSpacing: 1.1,
    });
    if (i < phases.length - 1) addArrow(slide, px + 158, 505, 18, 12, C.red);
    px += 218;
  });

  addText(slide, "AI 只做辅助：发布、签认、验收仍由人完成", { left: 330, top: 622, width: 620, height: 26 }, {
    fontSize: 15,
    bold: true,
    color: C.red,
    alignment: "center",
  });

  slide.speakerNotes.text =
    "实施节奏参考桩基工程文档管理智能体工作计划.pdf：第5-6周基础功能，第7周完善施工功能，第8周接入AI模型，第9-10周AI检查与报告，第11-12周UI、移动端和整合验收。AI只做辅助，发布、签认、验收仍由人完成。";
}

// Export PNGs and PPTX draft
await fs.mkdir(OUT, { recursive: true });
for (const [index, slide] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(OUT, `slide-${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
}
const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
await fs.writeFile(path.join(OUT, "deck-montage.webp"), new Uint8Array(await montage.arrayBuffer()));
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(path.join(OUT, "draft.pptx"));
console.log("DRAFT_OK", OUT);


// Validate and finalize the editable PPTX.
const { finalizePresentation } = await import(
  pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href
);
const stagingDir = path.join(OUT, ".finalizer");
await fs.mkdir(stagingDir, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });
const candidatePath = path.join(stagingDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const requirements = {
  explicitTotalSlideCount: 9,
  requiredNativeTableOwnerSlides: [3],
  requiredNativeChartOwnerSlides: [],
  fontPolicy: { basis: "design", families: [FONT] },
};
const result = await finalizePresentation({
  ...requirements,
  workspaceDir: WORKSPACE_DIR,
  candidatePath,
  finalPath: FINAL_PPTX,
  expectedSlideSizeEmu: "12192000,6858000",
  pythonExecutable: RUNTIME_PYTHON,
  integrityValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(SKILL_DIR, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: [
    "--expected-slide-size-emu", "12192000,6858000",
    "--validate-bullet-geometry",
    "--validate-heading-fit",
    "--require-native-table-slide", "3",
  ],
  requiredNativeTableOwnerSlides: requirements.requiredNativeTableOwnerSlides,
  fontPolicy: requirements.fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "final-validation.json"),
});
console.log("FINAL_OK", FINAL_PPTX);
console.log(JSON.stringify(result, null, 2));
