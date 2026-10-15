import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { config } from '../config.js';
import { hashPassword } from '../security.js';

const schemaPath = path.join(import.meta.dirname, 'schema.sql');
const catalogPath = path.join(import.meta.dirname, '..', 'data', 'catalog.json');

const UNIT_SEED = [
  ['owner', '工程建设单位', '建设单位'],
  ['geotech', '地质勘察单位', '勘察单位'],
  ['design', '工程设计单位', '设计单位'],
  ['test_pile_contractor', '设计试桩单位', '施工单位'],
  ['test_pile_testing', '设计试桩检测单位', '检测单位'],
  ['government', '政府审查单位', '政府单位'],
  ['general_contractor', '工程总包单位', '总包单位'],
  ['pile_subcontractor', '桩基分包单位', '分包单位'],
  ['supervision', '工程监理单位', '监理单位'],
  ['testing_monitoring', '检测监测单位', '检测监测单位'],
  ['acceptance_test_pile', '验收试桩单位', '施工/检测单位'],
  ['tbd', '待定单位', '待定'],
];

const PHASE_SEED = [
  '前期调研阶段',
  '地质勘察阶段',
  '设计试桩阶段',
  '工程设计阶段',
  '桩基施工阶段',
  '验收试桩阶段',
  '运维监测阶段',
];

const USER_SEED = [
  ['admin', '系统管理员', null, '系统管理员'],
  ['owner_viewer', '建设单位资料员', 'owner', '查看人员'],
  ['contractor', '总包资料员', 'general_contractor', '资料员'],
  ['pile_subcontractor', '桩基分包资料员', 'pile_subcontractor', '资料员'],
  ['supervisor', '监理资料员', 'supervision', '资料员'],
  ['testing', '检测监测资料员', 'testing_monitoring', '资料员'],
];

const DEMO_PASSWORD = 'Demo@123456';

function insertId(result) {
  return Number(result.lastInsertRowid);
}

export function openDatabase(options = {}) {
  const dbPath = options.dbPath ?? config.dbPath;
  if (dbPath !== ':memory:') {
    fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  }

  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA foreign_keys = ON;');
  db.exec(fs.readFileSync(schemaPath, 'utf8'));
  if (options.seed !== false) seedDatabase(db);
  return db;
}

export function seedDatabase(db) {
  const existing = db.prepare('SELECT COUNT(*) AS count FROM projects').get();
  if (Number(existing.count) > 0) return;

  const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));

  db.exec('BEGIN IMMEDIATE;');
  try {
    const insertUnit = db.prepare(`
      INSERT OR IGNORE INTO units (unit_code, unit_name, unit_type)
      VALUES (?, ?, ?)
    `);
    for (const unit of UNIT_SEED) insertUnit.run(...unit);

    const units = new Map(
      db.prepare('SELECT unit_id, unit_code FROM units').all()
        .map((row) => [row.unit_code, Number(row.unit_id)]),
    );

    const insertUser = db.prepare(`
      INSERT INTO users (username, real_name, phone, password_hash, unit_id)
      VALUES (?, ?, ?, ?, ?)
    `);
    const users = new Map();
    for (const [username, realName, unitCode, role] of USER_SEED) {
      const result = insertUser.run(
        username,
        realName,
        null,
        hashPassword(DEMO_PASSWORD),
        unitCode ? units.get(unitCode) : null,
      );
      users.set(username, { userId: insertId(result), unitId: unitCode ? units.get(unitCode) : null, role });
    }

    const projectResult = db.prepare(`
      INSERT INTO projects (
        project_code, project_name, location, description, status, start_date
      ) VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      'SH-ZJ-2026-001',
      '上海市综合体桩基工程',
      '上海市',
      '桩基工程全过程文档管理与质量预警平台示范项目',
      '进行中',
      '2026-09-01',
    );
    const projectId = insertId(projectResult);

    const insertPhase = db.prepare(`
      INSERT INTO project_phases (project_id, phase_name, phase_order, status)
      VALUES (?, ?, ?, ?)
    `);
    const phases = new Map();
    PHASE_SEED.forEach((name, index) => {
      const order = index + 1;
      let status = '未开始';
      if (order <= 4) status = '已完成';
      if (order === 5) status = '进行中';
      const result = insertPhase.run(projectId, name, order, status);
      phases.set(order, insertId(result));
    });

    const insertDocType = db.prepare(`
      INSERT INTO doc_types (
        phase_id, doc_code, doc_name, responsible_unit_id,
        is_required, need_approval, file_formats, description
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    for (const item of catalog) {
      insertDocType.run(
        phases.get(item.phase_order),
        item.doc_code,
        item.doc_name,
        units.get(item.responsible_unit_code) ?? units.get('tbd'),
        item.is_required ? 1 : 0,
        item.need_approval ? 1 : 0,
        item.file_formats,
        item.description,
      );
    }

    const insertRole = db.prepare(`
      INSERT INTO user_project_roles (user_id, project_id, unit_id, role)
      VALUES (?, ?, ?, ?)
    `);
    for (const user of users.values()) {
      insertRole.run(user.userId, projectId, user.unitId, user.role);
    }

    const insertPile = db.prepare(`
      INSERT INTO piles (
        project_id, pile_no, bim_id, x_coord, y_coord, pile_type, design_depth, status
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    `);
    for (let index = 1; index <= 12; index += 1) {
      const pileNo = `ZH-${String(index).padStart(3, '0')}`;
      insertPile.run(
        projectId,
        pileNo,
        `BIM-${pileNo}`,
        Number((100.2 + index * 1.35).toFixed(2)),
        Number((200.4 + index * 0.88).toFixed(2)),
        index % 3 === 0 ? '钻孔灌注桩' : '预制桩',
        42.5 + (index % 4),
        index <= 4 ? '已完成' : '待施工',
      );
    }

    db.exec('COMMIT;');
  } catch (error) {
    db.exec('ROLLBACK;');
    throw error;
  }
}

export function inTransaction(db, callback) {
  db.exec('BEGIN IMMEDIATE;');
  try {
    const result = callback();
    db.exec('COMMIT;');
    return result;
  } catch (error) {
    db.exec('ROLLBACK;');
    throw error;
  }
}
