import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

process.env.RUNTIME_NODE_MODULES = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
process.env.CODEX_PRIMARY_RUNTIME_NODE_MODULES = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";

const WORKSPACE_DIR = "/Users/kylie/Desktop/桩基工程全过程管理";
const OUT = path.join(WORKSPACE_DIR, ".codex-build/pile-construction-deck/construction-artifacts");
const SKILL_DIR = "/Users/kylie/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations";
const RUNTIME_PYTHON = "/Users/kylie/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3";
const FINAL_PPTX = path.join(WORKSPACE_DIR, "output/桩基施工管理专题汇报.pptx");
const FONT = "Hiragino Sans GB";
const C = {
  navy: "#102A43", navy2: "#173F5F", red: "#B4232C", redSoft: "#FBE9EB",
  blue: "#2563A6", blueSoft: "#EAF2FA", teal: "#0F8B8D", tealSoft: "#E7F5F5",
  ink: "#1C2733", gray: "#5F6B7A", muted: "#8491A2", light: "#F4F7FA",
  border: "#DCE4EC", white: "#FFFFFF", amber: "#B7791F", amberSoft: "#FFF4DD",
};
const W = 1280, H = 720;

function addText(slide, text, pos, style = {}) {
  const shape = slide.shapes.add({ geometry: "textbox", position: pos, fill: "none", line: { style: "solid", fill: "none", width: 0 } });
  shape.text = text;
  shape.text.style = { typeface: FONT, color: C.ink, fontSize: 16, verticalAlignment: "top", wrap: "square", ...style };
  return shape;
}
function addCard(slide, pos, opts = {}) {
  return slide.shapes.add({ geometry: "roundRect", position: pos, fill: opts.fill ?? C.light, line: { style: "solid", fill: opts.line ?? C.border, width: opts.lineWidth ?? 1 }, borderRadius: "rounded-xl" });
}
function addBar(slide, pos, color = C.border) {
  return slide.shapes.add({ geometry: "rect", position: pos, fill: color, line: { style: "solid", fill: "none", width: 0 } });
}
function addArrow(slide, left, top, width = 22, height = 16, color = C.red, direction = "right") {
  return slide.shapes.add({ geometry: direction === "right" ? "rightArrow" : "downArrow", position: { left, top, width, height }, fill: color, line: { style: "solid", fill: "none", width: 0 } });
}
function addChip(slide, text, left, top, width, opts = {}) {
  const card = slide.shapes.add({ geometry: "roundRect", position: { left, top, width, height: opts.height ?? 30 }, fill: opts.fill ?? C.white, line: { style: "solid", fill: opts.line ?? C.border, width: 1 }, borderRadius: "rounded-full" });
  card.text = text;
  card.text.style = { typeface: FONT, fontSize: opts.fontSize ?? 13, bold: opts.bold ?? false, color: opts.color ?? C.navy2, alignment: "center", verticalAlignment: "middle", insets: { left: 9, right: 9, top: 0, bottom: 0 } };
  return card;
}
function header(slide, title, subtitle, index) {
  slide.background.fill = C.white;
  addBar(slide, { left: 64, top: 42, width: 38, height: 5 }, C.red);
  addText(slide, title, { left: 64, top: 62, width: 1120, height: 52 }, { fontSize: 31, bold: true, color: C.navy, lineSpacing: 1.05 });
  if (subtitle) addText(slide, subtitle, { left: 64, top: 116, width: 1120, height: 30 }, { fontSize: 15, color: C.gray });
  addText(slide, "桩基施工管理专题汇报", { left: 64, top: 686, width: 360, height: 20 }, { fontSize: 10, color: C.muted });
  addText(slide, String(index).padStart(2, "0"), { left: 1180, top: 684, width: 36, height: 20 }, { fontSize: 10, color: C.muted, alignment: "right" });
}
function bullets(slide, items, left, top, width, height, opts = {}) {
  const paragraphs = items.map((item) => ({ bulletCharacter: "•", marginLeft: 18, indent: -10, spaceAfter: opts.spaceAfter ?? 7, runs: [item] }));
  return addText(slide, paragraphs, { left, top, width, height }, { fontSize: opts.fontSize ?? 15, color: opts.color ?? C.ink, lineSpacing: opts.lineSpacing ?? 1.15 });
}
function styleTableHeader(table, cols) {
  for (let c = 0; c < cols; c += 1) {
    const cell = table.getCell(0, c);
    cell.fill = C.navy;
    cell.text.style = { typeface: FONT, fontSize: 14, bold: true, color: C.white, verticalAlignment: "middle", insets: { left: 10, right: 8, top: 5, bottom: 5 } };
  }
}
function styleTableBody(table, rows, cols, opts = {}) {
  for (let r = 1; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const cell = table.getCell(r, c);
      cell.fill = r % 2 === 0 ? C.light : C.white;
      cell.text.style = { typeface: FONT, fontSize: opts.fontSize ?? 13.2, color: C.ink, bold: c === 0, verticalAlignment: "middle", insets: { left: 10, right: 8, top: 5, bottom: 5 } };
    }
  }
}
function metric(slide, value, label, left, top, width, color = C.red) {
  addText(slide, value, { left, top, width, height: 42 }, { fontSize: 28, bold: true, color, alignment: "center" });
  addText(slide, label, { left, top: top + 42, width, height: 24 }, { fontSize: 12.5, color: C.gray, alignment: "center" });
}

const presentation = Presentation.create({ slideSize: { width: W, height: H } });

// 1 Cover
{
  const slide = presentation.slides.add();
  slide.background.fill = C.navy;
  addBar(slide, { left: 0, top: 0, width: 16, height: H }, C.red);
  addText(slide, "桩基工程全过程管理平台", { left: 72, top: 74, width: 520, height: 26 }, { fontSize: 14, bold: true, color: "#AFC5D9" });
  addText(slide, "桩基施工\n管理汇报", { left: 72, top: 170, width: 700, height: 150 }, { fontSize: 54, bold: true, color: C.white, lineSpacing: 1.08 });
  addText(slide, "施工组织 · 过程控制 · 检测验收 · 资料闭环", { left: 76, top: 350, width: 700, height: 46 }, { fontSize: 20, color: "#D9E5F0" });
  const chips = ["施工准备", "关键工序", "质量验收", "一桩一档"];
  let x = 76;
  for (const chip of chips) { addChip(slide, chip, x, 442, 138, { fill: "rgba(255,255,255,0.08)", line: "#42627E", color: C.white, fontSize: 13 }); x += 152; }
  addBar(slide, { left: 916, top: 180, width: 250, height: 24 }, "#7F99B1");
  for (let i = 0; i < 7; i += 1) {
    const px = 936 + i * 34;
    addBar(slide, { left: px, top: 198, width: 8, height: 260 }, i % 2 === 0 ? "#D9E5F0" : "#AFC5D9");
    slide.shapes.add({ geometry: "ellipse", position: { left: px - 1, top: 452, width: 10, height: 10 }, fill: C.red, line: { style: "solid", fill: "none", width: 0 } });
  }
  addText(slide, "PILE CONSTRUCTION", { left: 914, top: 496, width: 250, height: 24 }, { fontSize: 11, bold: true, color: "#8FA8BD", alignment: "center" });
  addText(slide, "以钻孔灌注桩为主线；预制桩可按沉桩工艺替换相应工序", { left: 76, top: 626, width: 760, height: 24 }, { fontSize: 11, color: "#9FB3C6" });
  slide.speakerNotes.text = "桩基施工管理专题汇报封面。适用于施工组织、过程控制、检测验收和资料管理汇报。以钻孔灌注桩为主线，预制桩可按沉桩工艺替换。";
}

// 2 Overview
{
  const slide = presentation.slides.add();
  header(slide, "施工管理围绕一条主线展开", "从施工准备到资料移交，形成可检查、可追溯的管理闭环。", 2);
  const steps = ["施工准备", "过程施工", "检测监测", "验收整改", "资料移交"];
  steps.forEach((s, i) => {
    const left = 64 + i * 228;
    addCard(slide, { left, top: 174, width: 198, height: 86 }, { fill: i === 0 ? C.blueSoft : i === 4 ? C.redSoft : C.light });
    addText(slide, String(i + 1).padStart(2, "0"), { left: left + 16, top: 188, width: 34, height: 18 }, { fontSize: 11, bold: true, color: i === 4 ? C.red : C.blue });
    addText(slide, s, { left: left + 16, top: 212, width: 160, height: 28 }, { fontSize: 18, bold: true, color: C.navy, alignment: "center" });
    if (i < steps.length - 1) addArrow(slide, left + 204, 210, 18, 14, C.red);
  });
  const goals = [["质量", "一次验收合格"], ["安全", "过程风险受控"], ["进度", "桩机与工序匹配"], ["资料", "一桩一档齐全"]];
  goals.forEach(([t, d], i) => {
    const left = 64 + i * 286;
    addCard(slide, { left, top: 312, width: 262, height: 126 }, { fill: C.white });
    addText(slide, t, { left: left + 20, top: 332, width: 80, height: 30 }, { fontSize: 22, bold: true, color: C.red });
    addText(slide, d, { left: left + 20, top: 378, width: 220, height: 24 }, { fontSize: 14, color: C.gray });
  });
  addCard(slide, { left: 64, top: 468, width: 1152, height: 84 }, { fill: C.navy });
  addText(slide, "以桩为主线  ·  以记录为证据  ·  以验收为节点", { left: 86, top: 490, width: 1108, height: 36 }, { fontSize: 24, bold: true, color: C.white, alignment: "center" });
  slide.speakerNotes.text = "施工管理总览：准备、施工、检测、验收、资料五段闭环；目标是质量、安全、进度、资料四个维度同时受控。";
}

// 3 Preparation
{
  const slide = presentation.slides.add();
  header(slide, "施工准备决定后续能否连续施工", "技术、现场、资源和报审四类准备必须同步完成。", 3);
  const cards = [
    ["技术准备", "图纸会审、设计交底\n专项施工方案、技术交底", C.blueSoft, C.blue],
    ["现场准备", "三通一平、测量控制点\n桩位复核、试桩/首件", C.tealSoft, C.teal],
    ["资源准备", "桩机、人员、钢筋、混凝土\n检测与监测资源", C.light, C.navy2],
    ["报审准备", "分包资质、人员机械报审\n开工报告、监理报审", C.redSoft, C.red],
  ];
  cards.forEach(([title, desc, fill, accent], i) => {
    const left = 64 + i * 286;
    addCard(slide, { left, top: 174, width: 262, height: 174 }, { fill });
    addText(slide, title, { left: left + 20, top: 196, width: 220, height: 32 }, { fontSize: 21, bold: true, color: accent });
    addText(slide, desc, { left: left + 20, top: 246, width: 220, height: 58 }, { fontSize: 14, color: C.ink, lineSpacing: 1.3 });
  });
  addCard(slide, { left: 64, top: 380, width: 1152, height: 166 }, { fill: C.white });
  addText(slide, "开工条件检查表", { left: 88, top: 400, width: 220, height: 28 }, { fontSize: 20, bold: true, color: C.navy });
  bullets(slide, ["施工图审查完成，设计交底完成", "专项施工方案批准，技术交底完成", "测量控制点复核，桩位放线完成", "分包资质、人员、机械、材料报审完成", "试桩/首件验收完成，监理开工条件核查通过"], 90, 442, 1060, 84, { fontSize: 14, spaceAfter: 4 });
  slide.speakerNotes.text = "施工准备分为技术、现场、资源、报审四类。开工条件检查表建议作为系统硬门槛，未完成不能签发开工令。";
}

// 4 Overall flow
{
  const slide = presentation.slides.add();
  header(slide, "施工总体流程分为八个节点", "流程按“准备—成桩—检测—验收”推进，每个节点都有记录输出。", 4);
  const steps = [
    ["1", "测量放线", "坐标 / 轴线 / 标高"], ["2", "护筒埋设", "中心 / 垂直度 / 埋深"],
    ["3", "成孔或沉桩", "孔径 / 孔深 / 垂直度"], ["4", "清孔或接桩", "沉渣 / 接头 / 标高"],
    ["5", "钢筋笼", "规格 / 间距 / 保护层"], ["6", "混凝土或连接", "导管 / 坍落度 / 连续"],
    ["7", "桩头处理", "凿除 / 锚固 / 标高"], ["8", "检测验收", "报告 / 整改 / 归档"],
  ];
  steps.forEach(([num, title, desc], i) => {
    const row = i < 4 ? 0 : 1;
    const col = i % 4;
    const left = 64 + col * 286;
    const top = 166 + row * 176;
    addCard(slide, { left, top, width: 252, height: 106 }, { fill: row === 0 ? C.blueSoft : C.light });
    addText(slide, num, { left: left + 16, top: top + 14, width: 32, height: 24 }, { fontSize: 13, bold: true, color: row === 0 ? C.blue : C.red });
    addText(slide, title, { left: left + 48, top: top + 12, width: 180, height: 28 }, { fontSize: 17, bold: true, color: C.navy });
    addText(slide, desc, { left: left + 18, top: top + 56, width: 214, height: 34 }, { fontSize: 12.5, color: C.gray, lineSpacing: 1.1 });
    if (col < 3) addArrow(slide, left + 258, top + 44, 22, 18, row === 0 ? C.blue : C.teal);
  });
  addArrow(slide, 1138, 286, 20, 44, C.red, "down");
  addCard(slide, { left: 64, top: 536, width: 1152, height: 78 }, { fill: C.redSoft, line: "#E8BFC3" });
  addText(slide, "关键控制", { left: 88, top: 552, width: 120, height: 24 }, { fontSize: 14, bold: true, color: C.red });
  addText(slide, "桩位  ·  垂直度  ·  孔深  ·  沉渣  ·  混凝土  ·  桩头", { left: 204, top: 550, width: 970, height: 30 }, { fontSize: 20, bold: true, color: C.navy, alignment: "center" });
  slide.speakerNotes.text = "施工总体流程8节点：测量放线、护筒埋设、成孔或沉桩、清孔或接桩、钢筋笼、混凝土或连接、桩头处理、检测验收。";
}

// 5 Bored pile key process
{
  const slide = presentation.slides.add();
  header(slide, "以钻孔灌注桩为例的关键工序", "从成孔到桩头处理，每一道工序都要形成对应记录。", 5);
  const steps = ["测量放线", "护筒埋设", "成孔", "清孔", "钢筋笼", "导管", "水下混凝土", "后注浆", "桩头处理"];
  const start = 54, boxW = 120, gap = 12;
  steps.forEach((s, i) => {
    const left = start + i * (boxW + gap);
    addCard(slide, { left, top: 184, width: boxW, height: 88 }, { fill: i < 2 ? C.blueSoft : i < 4 ? C.tealSoft : i < 8 ? C.light : C.redSoft });
    addText(slide, s, { left: left + 8, top: 206, width: boxW - 16, height: 42 }, { fontSize: 14, bold: true, color: i < 2 ? C.blue : i < 4 ? C.teal : i < 8 ? C.navy : C.red, alignment: "center", lineSpacing: 1.1 });
    addText(slide, String(i + 1).padStart(2, "0"), { left: left + 8, top: 248, width: boxW - 16, height: 16 }, { fontSize: 9.5, color: C.muted, alignment: "center" });
    if (i < steps.length - 1) addArrow(slide, left + boxW + 1, 220, 10, 12, C.red);
  });
  addCard(slide, { left: 64, top: 314, width: 560, height: 268 }, { fill: C.light });
  addText(slide, "关键工序要点", { left: 88, top: 334, width: 220, height: 30 }, { fontSize: 21, bold: true, color: C.navy });
  bullets(slide, ["成孔：控制孔径、孔深、垂直度和沉渣", "钢筋笼：控制规格、间距、长度和保护层", "混凝土：控制导管埋深、坍落度和连续浇筑", "后注浆：控制压力、水泥量和注浆时间", "桩头：控制凿除标高、钢筋锚固和桩顶质量"], 92, 380, 500, 176, { fontSize: 14.5, spaceAfter: 8 });
  addCard(slide, { left: 650, top: 314, width: 566, height: 268 }, { fill: C.white });
  addText(slide, "工序记录", { left: 674, top: 334, width: 220, height: 30 }, { fontSize: 21, bold: true, color: C.navy });
  bullets(slide, ["成孔记录 / 沉桩记录", "钢筋笼制作及安装检查记录", "混凝土浇筑记录 / 后注浆记录", "隐蔽工程验收记录", "现场照片 / 视频"], 678, 380, 500, 160, { fontSize: 14.5, spaceAfter: 8 });
  addText(slide, "预制桩替换：成孔/清孔/混凝土 → 沉桩/接桩/桩头处理", { left: 100, top: 608, width: 1080, height: 24 }, { fontSize: 13, color: C.gray, alignment: "center" });
  slide.speakerNotes.text = "以钻孔灌注桩为例的关键工序：测量放线、护筒埋设、成孔、清孔、钢筋笼、导管、水下混凝土、后注浆、桩头处理。预制桩按沉桩/接桩工艺替换。";
}

// 6 Quality control table
{
  const slide = presentation.slides.add();
  header(slide, "关键质量控制点必须落到记录", "每个控制点都要有检查动作、验收标准和对应记录。", 6);
  const rows = [
    ["工序", "关键控制点", "对应记录"],
    ["测量放线", "桩位坐标、轴线、标高", "测量复核记录"],
    ["成孔", "孔径、孔深、垂直度、沉渣", "成孔记录"],
    ["钢筋笼", "规格、间距、长度、保护层", "钢筋笼检查记录"],
    ["混凝土", "坍落度、导管埋深、连续浇筑", "混凝土浇筑记录"],
    ["后注浆", "注浆压力、水泥量、时间", "后注浆记录"],
    ["桩头 / 接桩", "凿除标高、钢筋锚固、焊缝质量", "桩头/接桩记录"],
  ];
  const table = slide.tables.add({ rows: 7, columns: 3, left: 64, top: 176, width: 1152, height: 390, columnWidths: [180, 500, 472], values: rows });
  styleTableHeader(table, 3);
  styleTableBody(table, 7, 3, { fontSize: 14 });
  table.borders.assign({ style: "solid", fill: C.border, width: 1 });
  addCard(slide, { left: 64, top: 590, width: 1152, height: 54 }, { fill: C.redSoft, line: "#E8BFC3" });
  addText(slide, "检查动作必须与记录同步：没有记录，视为没有发生；没有验收，不得进入下一道工序。", { left: 84, top: 604, width: 1112, height: 26 }, { fontSize: 15, bold: true, color: C.red, alignment: "center" });
  slide.speakerNotes.text = "关键质量控制表：测量放线、成孔、钢筋笼、混凝土、后注浆、桩头/接桩。每个控制点必须对应检查记录。";
}

// 7 Testing & monitoring
{
  const slide = presentation.slides.add();
  header(slide, "检测与监测是施工质量的独立验证", "检测结果和监测预警必须进入问题闭环。", 7);
  addCard(slide, { left: 64, top: 174, width: 560, height: 350 }, { fill: C.blueSoft });
  addText(slide, "检测", { left: 88, top: 194, width: 120, height: 30 }, { fontSize: 23, bold: true, color: C.blue });
  bullets(slide, ["低应变：桩身完整性普查", "声波透射：灌注桩完整性", "钻芯：混凝土质量与桩长", "静载：单桩承载力", "高应变：承载力与完整性辅助"], 92, 242, 500, 180, { fontSize: 14.5, spaceAfter: 8 });
  addCard(slide, { left: 92, top: 444, width: 504, height: 54 }, { fill: C.white });
  addText(slide, "不合格 → 问题单 → 整改 → 复检 → 关闭", { left: 106, top: 458, width: 476, height: 24 }, { fontSize: 13.5, bold: true, color: C.red, alignment: "center" });

  addCard(slide, { left: 656, top: 174, width: 560, height: 350 }, { fill: C.tealSoft });
  addText(slide, "监测", { left: 680, top: 194, width: 120, height: 30 }, { fontSize: 23, bold: true, color: C.teal });
  bullets(slide, ["基坑及周边沉降", "支护结构水平位移", "地下水位变化", "周边建筑物/管线变形", "监测频率与预警阈值"], 684, 242, 500, 180, { fontSize: 14.5, spaceAfter: 8 });
  addCard(slide, { left: 684, top: 444, width: 504, height: 54 }, { fill: C.white });
  addText(slide, "预警 → 会商 → 处置 → 复测 → 关闭", { left: 698, top: 458, width: 476, height: 24 }, { fontSize: 13.5, bold: true, color: C.teal, alignment: "center" });

  addText(slide, "所有检测报告、监测预警和整改关闭必须留痕并可追溯", { left: 200, top: 568, width: 880, height: 28 }, { fontSize: 17, bold: true, color: C.navy2, alignment: "center" });
  slide.speakerNotes.text = "检测包括低应变、声波透射、钻芯、静载、高应变；监测包括沉降、位移、水位、周边建筑与管线。检测不合格和监测预警都必须转问题闭环。";
}

// 8 Acceptance & issue closure
{
  const slide = presentation.slides.add();
  header(slide, "验收与问题闭环决定工序能否继续", "先验收、后转序；不合格必须整改、复查、关闭。", 8);
  const normal = ["分包自检", "总包复核", "监理验收", "检测确认", "资料归档"];
  normal.forEach((s, i) => {
    const left = 64 + i * 228;
    addCard(slide, { left, top: 184, width: 198, height: 82 }, { fill: i === 4 ? C.tealSoft : C.light });
    addText(slide, s, { left: left + 12, top: 208, width: 174, height: 28 }, { fontSize: 17, bold: true, color: i === 4 ? C.teal : C.navy, alignment: "center" });
    if (i < normal.length - 1) addArrow(slide, left + 202, 216, 20, 16, C.teal);
  });
  addText(slide, "正常验收流程", { left: 64, top: 154, width: 180, height: 22 }, { fontSize: 12, bold: true, color: C.teal });
  const issue = ["不合格/预警", "整改通知", "责任单位整改", "监理复查", "关闭"];
  issue.forEach((s, i) => {
    const left = 64 + i * 228;
    addCard(slide, { left, top: 342, width: 198, height: 82 }, { fill: i === 0 ? C.redSoft : C.white });
    addText(slide, s, { left: left + 12, top: 366, width: 174, height: 28 }, { fontSize: 16, bold: true, color: i === 0 ? C.red : C.navy, alignment: "center" });
    if (i < issue.length - 1) addArrow(slide, left + 202, 374, 20, 16, C.red);
  });
  addText(slide, "问题闭环流程", { left: 64, top: 312, width: 180, height: 22 }, { fontSize: 12, bold: true, color: C.red });
  addCard(slide, { left: 64, top: 492, width: 1152, height: 104 }, { fill: C.navy });
  addText(slide, "未验收不得进入下一道工序", { left: 88, top: 514, width: 480, height: 36 }, { fontSize: 26, bold: true, color: C.white });
  addText(slide, "未关闭不得进入阶段验收", { left: 720, top: 516, width: 450, height: 36 }, { fontSize: 24, bold: true, color: "#FFD5D8", alignment: "right" });
  slide.speakerNotes.text = "验收流程：分包自检、总包复核、监理验收、检测确认、资料归档。问题闭环：不合格/预警、整改通知、整改、监理复查、关闭。未验收不得转序，未关闭不得阶段验收。";
}

// 9 Documents
{
  const slide = presentation.slides.add();
  header(slide, "施工资料按一桩一档和资料包双线管理", "32类施工资料形成资料包，单桩形成一桩一档。", 9);
  addCard(slide, { left: 64, top: 174, width: 404, height: 396 }, { fill: C.light });
  addText(slide, "施工资料包", { left: 88, top: 194, width: 240, height: 30 }, { fontSize: 21, bold: true, color: C.navy });
  const packs = [["5.1", "总包统筹", "6类"], ["5.2", "分包执行", "8类"], ["5.3", "监理控制", "9类"], ["5.4", "检测监测", "9类"]];
  packs.forEach(([code, name, count], i) => {
    const top = 244 + i * 72;
    addChip(slide, code, 88, top, 54, { height: 28, fill: C.white, color: C.red, bold: true, fontSize: 12 });
    addText(slide, name, { left: 154, top: top - 2, width: 150, height: 28 }, { fontSize: 17, bold: true, color: C.navy });
    addText(slide, count, { left: 322, top: top - 2, width: 70, height: 28 }, { fontSize: 14, bold: true, color: C.navy2, alignment: "right" });
  });
  addCard(slide, { left: 496, top: 174, width: 720, height: 396 }, { fill: C.white });
  addText(slide, "一桩一档", { left: 520, top: 194, width: 240, height: 30 }, { fontSize: 21, bold: true, color: C.navy });
  bullets(slide, ["桩位基本信息与设计参数", "施工记录（成孔/钢筋笼/浇筑/沉桩/注浆）", "隐蔽验收、检验批与旁站记录", "检测报告与复检记录", "现场照片/视频", "问题、整改与设计变更"], 524, 242, 620, 210, { fontSize: 15, spaceAfter: 9 });
  const statuses = ["未上传", "草稿", "审核中", "已批准", "已发布", "过期"];
  let x = 524; let y = 492;
  statuses.forEach((s, i) => { addChip(slide, s, x, y, 92, { height: 28, fill: i === 4 ? C.tealSoft : i === 5 ? C.amberSoft : C.light, line: i === 4 ? C.teal : i === 5 ? "#E8C98D" : C.border, color: i === 4 ? C.teal : i === 5 ? C.amber : C.gray, fontSize: 11.5 }); x += 100; });
  addText(slide, "资料状态随流程自动更新，归档后只读留痕", { left: 524, top: 536, width: 640, height: 22 }, { fontSize: 12.5, color: C.gray });
  slide.speakerNotes.text = "施工资料按5.1总包6类、5.2分包8类、5.3监理9类、5.4检测监测9类组织；单桩形成一桩一档。资料来源：桩基工程全过程管理文档清单.xlsx。";
}

// 10 Progress, resources, risks
{
  const slide = presentation.slides.add();
  header(slide, "进度、资源与风险需要同步管理", "桩机、人员、材料和检测资源不匹配，会直接造成停窝工和质量风险。", 10);
  const cols = [
    ["进度", ["日计划 / 周计划", "桩机台班与完成桩数", "计划与实际对比", "延误原因与纠偏"], C.blueSoft, C.blue],
    ["资源", ["桩机、吊车、人员", "钢筋、混凝土供应", "检测与监测资源", "材料批次与进场计划"], C.tealSoft, C.teal],
    ["风险", ["塌孔、缩径、断桩", "桩位偏差、垂直度超标", "混凝土超灌、桩头缺陷", "监测预警、周边建筑变形"], C.redSoft, C.red],
  ];
  cols.forEach(([title, items, fill, accent], i) => {
    const left = 64 + i * 390;
    addCard(slide, { left, top: 174, width: 366, height: 358 }, { fill });
    addText(slide, title, { left: left + 22, top: 194, width: 260, height: 32 }, { fontSize: 23, bold: true, color: accent });
    bullets(slide, items, left + 22, 250, 320, 220, { fontSize: 14.5, spaceAfter: 11 });
  });
  addCard(slide, { left: 64, top: 558, width: 1152, height: 82 }, { fill: C.navy });
  addText(slide, "风险应对：发现异常 → 停工序 → 分析原因 → 制定措施 → 复验后恢复", { left: 88, top: 580, width: 1104, height: 30 }, { fontSize: 20, bold: true, color: C.white, alignment: "center" });
  slide.speakerNotes.text = "施工进度按日/周计划管理；资源重点关注桩机、人员、钢筋、混凝土和检测资源；风险重点包括塌孔、缩径、断桩、桩位偏差、混凝土超灌和监测预警。";
}

// 11 Summary
{
  const slide = presentation.slides.add();
  header(slide, "施工管理最终落到三个闭环", "流程闭环、质量闭环、资料闭环缺一不可。", 11);
  const items = [
    ["流程闭环", "准备 → 施工 → 验收 → 移交", C.blueSoft, C.blue],
    ["质量闭环", "自检 → 复核 → 监理 → 检测 → 整改", C.tealSoft, C.teal],
    ["资料闭环", "一桩一档 → 资料包 → 归档 → 移交", C.redSoft, C.red],
  ];
  items.forEach(([title, desc, fill, accent], i) => {
    const left = 64 + i * 390;
    addCard(slide, { left, top: 184, width: 366, height: 196 }, { fill });
    addText(slide, title, { left: left + 24, top: 210, width: 300, height: 36 }, { fontSize: 25, bold: true, color: accent });
    addText(slide, desc, { left: left + 24, top: 270, width: 300, height: 60 }, { fontSize: 16, color: C.ink, lineSpacing: 1.35 });
  });
  addCard(slide, { left: 64, top: 424, width: 1152, height: 134 }, { fill: C.navy });
  addText(slide, "以桩为主线  ·  以记录为证据  ·  以验收为节点  ·  以资料包为交付", { left: 88, top: 456, width: 1104, height: 34 }, { fontSize: 24, bold: true, color: C.white, alignment: "center" });
  addText(slide, "所有操作留痕，所有问题闭环，所有资料可追溯", { left: 88, top: 506, width: 1104, height: 28 }, { fontSize: 16, color: "#C9D9E7", alignment: "center" });
  addText(slide, "谢谢", { left: 568, top: 616, width: 144, height: 36 }, { fontSize: 22, bold: true, color: C.navy2, alignment: "center" });
  slide.speakerNotes.text = "总结：流程闭环、质量闭环、资料闭环。以桩为主线、以记录为证据、以验收为节点、以资料包为交付。";
}

await fs.mkdir(OUT, { recursive: true });
for (const [index, slide] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(OUT, `slide-${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
}
const pptx = await PresentationFile.exportPptx(presentation);
await pptx.save(path.join(OUT, "draft.pptx"));

const { finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, "container_tools/artifact_tool_utils.mjs")).href);
const stagingDir = path.join(OUT, ".finalizer");
await fs.mkdir(stagingDir, { recursive: true });
await fs.mkdir(path.dirname(FINAL_PPTX), { recursive: true });
const candidatePath = path.join(stagingDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const requirements = {
  explicitTotalSlideCount: 11,
  requiredNativeTableOwnerSlides: [6],
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
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit", "--require-native-table-slide", "6"],
  requiredNativeTableOwnerSlides: requirements.requiredNativeTableOwnerSlides,
  fontPolicy: requirements.fontPolicy,
  verifyArtifactToolImport: true,
  receiptPath: path.join(stagingDir, "final-validation.json"),
});
console.log("CONSTRUCTION_FINAL_OK", FINAL_PPTX);
console.log(JSON.stringify(result, null, 2));
