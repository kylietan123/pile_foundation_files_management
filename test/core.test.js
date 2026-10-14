import { after, before, describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { openDatabase } from '../src/db/database.js';
import { canUploadDocType, getUserProjectAccess } from '../src/permissions.js';
import { getDashboard, getPhaseDetails } from '../src/data-service.js';

let db;

before(() => {
  db = openDatabase({ dbPath: ':memory:' });
});

after(() => {
  db.close();
});

function userId(username) {
  return Number(db.prepare('SELECT user_id FROM users WHERE username = ?').get(username).user_id);
}

describe('数据库种子', () => {
  test('创建 7 个阶段、84 类全过程文档和 32 类施工文档', () => {
    assert.equal(Number(db.prepare('SELECT COUNT(*) AS count FROM project_phases').get().count), 7);
    assert.equal(Number(db.prepare('SELECT COUNT(*) AS count FROM doc_types').get().count), 84);
    assert.equal(Number(db.prepare(`
      SELECT COUNT(*) AS count
      FROM doc_types dt
      JOIN project_phases pp ON pp.phase_id = dt.phase_id
      WHERE pp.phase_order = 5
    `).get().count), 32);
  });

  test('文档类型绑定责任单位并保留审批要求字段', () => {
    const type = db.prepare(`
      SELECT dt.doc_code, u.unit_name, dt.need_approval
      FROM doc_types dt
      JOIN units u ON u.unit_id = dt.responsible_unit_id
      WHERE dt.doc_code = '5.2.1'
    `).get();
    assert.equal(type.unit_name, '桩基分包单位');
    assert.equal(Number(type.need_approval), 1);
  });
});

describe('单位上传权限', () => {
  test('总包只能上传 5.1，不能上传分包、监理或检测文档', () => {
    const contractor = userId('contractor');
    assert.equal(canUploadDocType(db, contractor, 1, 41), true);
    assert.equal(canUploadDocType(db, contractor, 1, 47), false);
    assert.equal(canUploadDocType(db, contractor, 1, 55), false);
    assert.equal(canUploadDocType(db, contractor, 1, 64), false);
  });

  test('分包、监理、检测账号分别只能上传各自负责的区块', () => {
    assert.equal(canUploadDocType(db, userId('pile_subcontractor'), 1, 47), true);
    assert.equal(canUploadDocType(db, userId('pile_subcontractor'), 1, 55), false);
    assert.equal(canUploadDocType(db, userId('supervisor'), 1, 55), true);
    assert.equal(canUploadDocType(db, userId('supervisor'), 1, 64), false);
    assert.equal(canUploadDocType(db, userId('testing'), 1, 64), true);
    assert.equal(canUploadDocType(db, userId('testing'), 1, 47), false);
  });

  test('建设单位账号可查看项目但不具备上传权限', () => {
    const viewer = userId('owner_viewer');
    const access = getUserProjectAccess(db, viewer, 1);
    assert.equal(access.hasAccess, true);
    assert.equal(access.canUpload, false);
    assert.equal(canUploadDocType(db, viewer, 1, 41), false);
  });

  test('系统管理员可跨单位维护文档', () => {
    const admin = userId('admin');
    assert.equal(canUploadDocType(db, admin, 1, 41), true);
    assert.equal(canUploadDocType(db, admin, 1, 72), true);
  });
});

describe('阶段台账', () => {
  test('施工阶段按四个责任单位分组', () => {
    const phase = db.prepare('SELECT phase_id FROM project_phases WHERE phase_order = 5').get();
    const detail = getPhaseDetails(db, userId('contractor'), 1, Number(phase.phase_id));
    assert.deepEqual(
      detail.groups.map((group) => group.responsible_unit_name),
      ['工程总包单位', '桩基分包单位', '工程监理单位', '检测监测单位'],
    );
    assert.equal(detail.progress.required, 32);
  });

  test('项目总览包含 7 个阶段统计', () => {
    const dashboard = getDashboard(db, userId('admin'), 1);
    assert.equal(dashboard.phases.length, 7);
    assert.equal(dashboard.summary.requiredCount, 82);
    assert.equal(dashboard.summary.documentCount, 0);
  });
});
