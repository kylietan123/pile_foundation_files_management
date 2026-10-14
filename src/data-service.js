import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { config } from './config.js';
import { HttpError } from './http.js';
import { canUploadDocType, getUserProjectAccess, writeAuditLog } from './permissions.js';
import { inTransaction } from './db/database.js';
import { sha256Buffer } from './security.js';

const ALLOWED_EXTENSIONS = new Set([
  '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.csv', '.txt', '.md',
  '.dwg', '.dxf', '.rvt', '.ifc', '.skp', '.model',
  '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tif', '.tiff', '.heic',
  '.mp4', '.mov', '.avi', '.mkv', '.m4v', '.webm',
  '.zip', '.rar', '.7z',
]);

function asNumber(value) {
  return value === null || value === undefined ? null : Number(value);
}

function normalizeDocument(row) {
  return {
    ...row,
    doc_id: Number(row.doc_id),
    doc_type_id: Number(row.doc_type_id),
    project_id: Number(row.project_id),
    current_version: Number(row.current_version),
  };
}

export function getProjectOrThrow(db, projectId) {
  const project = db.prepare(`
    SELECT project_id, project_code, project_name, location, description, status,
           start_date, end_date, created_at
    FROM projects
    WHERE project_id = ?
  `).get(projectId);
  if (!project) throw new HttpError(404, '项目不存在', 'PROJECT_NOT_FOUND');
  return { ...project, project_id: Number(project.project_id) };
}

export function requireProjectAccess(db, userId, projectId) {
  const project = getProjectOrThrow(db, projectId);
  const access = getUserProjectAccess(db, userId, projectId);
  if (!access.hasAccess) throw new HttpError(403, '无权访问该项目', 'PROJECT_FORBIDDEN');
  return { project, access };
}

export function listAccessibleProjects(db, userId) {
  const globalAdmin = db.prepare(`
    SELECT 1 AS ok
    FROM user_project_roles
    WHERE user_id = ? AND role = '系统管理员'
    LIMIT 1
  `).get(userId);

  if (globalAdmin) {
    return db.prepare(`
      SELECT project_id, project_code, project_name, location, status, created_at
      FROM projects
      ORDER BY created_at DESC, project_id DESC
    `).all().map((row) => ({ ...row, project_id: Number(row.project_id), roles: ['系统管理员'] }));
  }

  const rows = db.prepare(`
    SELECT
      p.project_id, p.project_code, p.project_name, p.location, p.status, p.created_at,
      upr.role, u.unit_name
    FROM projects p
    JOIN user_project_roles upr ON upr.project_id = p.project_id
    LEFT JOIN units u ON u.unit_id = upr.unit_id
    WHERE upr.user_id = ?
    ORDER BY p.created_at DESC, p.project_id DESC, upr.id
  `).all(userId);

  const projects = new Map();
  for (const row of rows) {
    const id = Number(row.project_id);
    if (!projects.has(id)) {
      projects.set(id, {
        project_id: id,
        project_code: row.project_code,
        project_name: row.project_name,
        location: row.location,
        status: row.status,
        created_at: row.created_at,
        roles: [],
      });
    }
    projects.get(id).roles.push({
      role: row.role,
      unit_name: row.unit_name || '系统管理',
    });
  }
  return [...projects.values()];
}

export function getDashboard(db, userId, projectId) {
  const { project, access } = requireProjectAccess(db, userId, projectId);

  const phaseRows = db.prepare(`
    SELECT
      pp.phase_id,
      pp.phase_name,
      pp.phase_order,
      pp.status,
      COUNT(DISTINCT dt.doc_type_id) AS doc_type_count,
      COUNT(DISTINCT CASE WHEN dt.is_required = 1 THEN dt.doc_type_id END) AS required_count,
      COUNT(DISTINCT CASE WHEN d.doc_id IS NOT NULL AND dt.is_required = 1 THEN dt.doc_type_id END) AS covered_count,
      COUNT(DISTINCT d.doc_id) AS document_count
    FROM project_phases pp
    LEFT JOIN doc_types dt ON dt.phase_id = pp.phase_id
    LEFT JOIN documents d ON d.doc_type_id = dt.doc_type_id
    WHERE pp.project_id = ?
    GROUP BY pp.phase_id
    ORDER BY pp.phase_order
  `).all(projectId).map((row) => {
    const required = Number(row.required_count);
    const covered = Number(row.covered_count);
    return {
      ...row,
      phase_id: Number(row.phase_id),
      phase_order: Number(row.phase_order),
      doc_type_count: Number(row.doc_type_count),
      required_count: required,
      covered_count: covered,
      document_count: Number(row.document_count),
      completion_percent: required === 0 ? 0 : Math.round((covered / required) * 100),
    };
  });

  const totalRequired = phaseRows.reduce((sum, row) => sum + row.required_count, 0);
  const totalCovered = phaseRows.reduce((sum, row) => sum + row.covered_count, 0);
  const totalDocuments = phaseRows.reduce((sum, row) => sum + row.document_count, 0);
  const pendingApprovals = Number(db.prepare(`
    SELECT COUNT(*) AS count
    FROM documents
    WHERE project_id = ? AND status = '待审核'
  `).get(projectId).count);
  const alertCount = Number(db.prepare(`
    SELECT COUNT(*) AS count
    FROM quality_alerts
    WHERE project_id = ? AND status = '待处理'
  `).get(projectId).count);

  const recentDocuments = db.prepare(`
    SELECT
      d.doc_id, d.doc_no, d.title, d.current_version, d.status, d.updated_at,
      dt.doc_name AS doc_type_name, pp.phase_name, pp.phase_order,
      u.unit_name AS upload_unit_name,
      uploader.real_name AS uploader_name
    FROM documents d
    JOIN doc_types dt ON dt.doc_type_id = d.doc_type_id
    JOIN project_phases pp ON pp.phase_id = dt.phase_id
    LEFT JOIN units u ON u.unit_id = d.unit_id
    LEFT JOIN users uploader ON uploader.user_id = d.uploader_id
    WHERE d.project_id = ?
    ORDER BY d.updated_at DESC, d.doc_id DESC
    LIMIT 8
  `).all(projectId).map(normalizeDocument);

  return {
    project,
    access: {
      isAdmin: access.isAdmin,
      canUpload: access.canUpload,
      roles: access.roles,
    },
    summary: {
      requiredCount: totalRequired,
      coveredCount: totalCovered,
      completionPercent: totalRequired === 0 ? 0 : Math.round((totalCovered / totalRequired) * 100),
      documentCount: totalDocuments,
      pendingApprovals,
      alertCount,
    },
    phases: phaseRows,
    recentDocuments,
  };
}

export function getPhaseDetails(db, userId, projectId, phaseId) {
  const { access } = requireProjectAccess(db, userId, projectId);
  const phase = db.prepare(`
    SELECT phase_id, project_id, phase_name, phase_order, status, start_date, end_date
    FROM project_phases
    WHERE phase_id = ? AND project_id = ?
  `).get(phaseId, projectId);
  if (!phase) throw new HttpError(404, '项目阶段不存在', 'PHASE_NOT_FOUND');

  const typeRows = db.prepare(`
    SELECT
      dt.doc_type_id, dt.doc_code, dt.doc_name, dt.responsible_unit_id,
      dt.is_required, dt.need_approval, dt.file_formats, dt.description,
      ru.unit_code AS responsible_unit_code,
      ru.unit_name AS responsible_unit_name,
      COUNT(DISTINCT d.doc_id) AS document_count,
      MAX(d.updated_at) AS latest_updated_at
    FROM doc_types dt
    JOIN units ru ON ru.unit_id = dt.responsible_unit_id
    LEFT JOIN documents d ON d.doc_type_id = dt.doc_type_id
    WHERE dt.phase_id = ?
    GROUP BY dt.doc_type_id
    ORDER BY dt.doc_code
  `).all(phaseId).map((row) => ({
    ...row,
    doc_type_id: Number(row.doc_type_id),
    responsible_unit_id: Number(row.responsible_unit_id),
    is_required: Boolean(row.is_required),
    need_approval: Boolean(row.need_approval),
    document_count: Number(row.document_count),
    can_upload: canUploadDocType(db, userId, projectId, Number(row.doc_type_id)),
    documents: [],
  }));

  const documentRows = db.prepare(`
    SELECT
      d.doc_id, d.doc_type_id, d.project_id, d.doc_no, d.title, d.current_version,
      d.status, d.created_at, d.updated_at,
      u.unit_name AS upload_unit_name,
      uploader.real_name AS uploader_name
    FROM documents d
    JOIN doc_types dt ON dt.doc_type_id = d.doc_type_id
    LEFT JOIN units u ON u.unit_id = d.unit_id
    LEFT JOIN users uploader ON uploader.user_id = d.uploader_id
    WHERE dt.phase_id = ? AND d.project_id = ?
    ORDER BY d.updated_at DESC, d.doc_id DESC
  `).all(phaseId, projectId).map(normalizeDocument);

  const typesById = new Map(typeRows.map((item) => [item.doc_type_id, item]));
  for (const document of documentRows) {
    typesById.get(document.doc_type_id)?.documents.push(document);
  }

  const groups = [];
  for (const docType of typeRows) {
    let group = groups.find((item) => item.responsible_unit_id === docType.responsible_unit_id);
    if (!group) {
      group = {
        responsible_unit_id: docType.responsible_unit_id,
        responsible_unit_code: docType.responsible_unit_code,
        responsible_unit_name: docType.responsible_unit_name,
        doc_types: [],
      };
      groups.push(group);
    }
    group.doc_types.push(docType);
  }

  const required = typeRows.filter((item) => item.is_required).length;
  const covered = typeRows.filter((item) => item.is_required && item.document_count > 0).length;
  return {
    phase: {
      ...phase,
      phase_id: Number(phase.phase_id),
      project_id: Number(phase.project_id),
      phase_order: Number(phase.phase_order),
    },
    progress: {
      required,
      covered,
      completion_percent: required === 0 ? 0 : Math.round((covered / required) * 100),
    },
    access: {
      isAdmin: access.isAdmin,
      roles: access.roles,
    },
    groups,
  };
}

export function getDocumentDetail(db, userId, projectId, documentId) {
  requireProjectAccess(db, userId, projectId);
  const document = db.prepare(`
    SELECT
      d.doc_id, d.doc_type_id, d.project_id, d.doc_no, d.title, d.current_version,
      d.status, d.file_hash, d.created_at, d.updated_at,
      dt.doc_code, dt.doc_name AS doc_type_name, dt.file_formats, dt.need_approval,
      pp.phase_id, pp.phase_name,
      ru.unit_name AS responsible_unit_name,
      iu.unit_name AS upload_unit_name,
      uploader.real_name AS uploader_name
    FROM documents d
    JOIN doc_types dt ON dt.doc_type_id = d.doc_type_id
    JOIN project_phases pp ON pp.phase_id = dt.phase_id
    JOIN units ru ON ru.unit_id = dt.responsible_unit_id
    LEFT JOIN units iu ON iu.unit_id = d.unit_id
    LEFT JOIN users uploader ON uploader.user_id = d.uploader_id
    WHERE d.doc_id = ? AND d.project_id = ?
  `).get(documentId, projectId);
  if (!document) throw new HttpError(404, '文档不存在', 'DOCUMENT_NOT_FOUND');

  const versions = db.prepare(`
    SELECT
      dv.version_id, dv.version_no, dv.file_name, dv.file_size, dv.mime_type,
      dv.file_hash, dv.change_log, dv.uploaded_at,
      u.real_name AS uploader_name,
      un.unit_name AS upload_unit_name
    FROM document_versions dv
    JOIN users u ON u.user_id = dv.uploader_id
    LEFT JOIN units un ON un.unit_id = u.unit_id
    WHERE dv.doc_id = ?
    ORDER BY dv.version_no DESC
  `).all(documentId).map((row) => ({
    ...row,
    version_id: Number(row.version_id),
    version_no: Number(row.version_no),
    file_size: Number(row.file_size),
  }));

  const approvals = db.prepare(`
    SELECT
      af.approval_id, af.version_id, af.role, af.action, af.comment, af.status,
      af.action_time, af.created_at,
      approver.real_name AS approver_name
    FROM approval_flows af
    LEFT JOIN users approver ON approver.user_id = af.approver_id
    WHERE af.doc_id = ?
    ORDER BY af.created_at DESC, af.approval_id DESC
  `).all(documentId);

  const piles = db.prepare(`
    SELECT p.pile_id, p.pile_no, p.bim_id, p.pile_type, p.design_depth, p.status
    FROM document_piles dp
    JOIN piles p ON p.pile_id = dp.pile_id
    WHERE dp.doc_id = ?
    ORDER BY p.pile_no
  `).all(documentId);

  return {
    document: normalizeDocument({
      ...document,
      need_approval: Boolean(document.need_approval),
    }),
    versions,
    approvals,
    piles,
    can_upload: canUploadDocType(db, userId, projectId, Number(document.doc_type_id)),
  };
}

export function listAuditLogs(db, userId, projectId, limit = 30) {
  requireProjectAccess(db, userId, projectId);
  return db.prepare(`
    SELECT
      al.log_id, al.action, al.entity_type, al.entity_id, al.details,
      al.created_at, al.ip_address,
      u.real_name AS user_name, un.unit_name
    FROM audit_logs al
    LEFT JOIN users u ON u.user_id = al.user_id
    LEFT JOIN units un ON un.unit_id = u.unit_id
    WHERE al.project_id = ?
    ORDER BY al.created_at DESC, al.log_id DESC
    LIMIT ?
  `).all(projectId, Math.min(Math.max(Number(limit) || 30, 1), 100)).map((row) => ({
    ...row,
    details: row.details ? JSON.parse(row.details) : null,
  }));
}

function stringField(formData, name, maxLength = 500) {
  const value = formData.get(name);
  return typeof value === 'string' ? value.trim().slice(0, maxLength) : '';
}

function getUploadedFile(formData) {
  const file = formData.get('file');
  if (!file || typeof file === 'string' || typeof file.arrayBuffer !== 'function') {
    throw new HttpError(400, '请选择要上传的文件', 'FILE_REQUIRED');
  }
  if (!file.name || file.size <= 0) {
    throw new HttpError(400, '上传文件为空', 'EMPTY_FILE');
  }
  if (file.size > config.maxUploadBytes) {
    throw new HttpError(413, `文件不能超过 ${Math.round(config.maxUploadBytes / 1024 / 1024)} MB`, 'FILE_TOO_LARGE');
  }

  const extension = path.extname(file.name).toLowerCase();
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    throw new HttpError(400, `不支持的文件类型：${extension || '无扩展名'}`, 'FILE_TYPE_NOT_ALLOWED');
  }

  return { file, extension };
}

async function storeFile(file, extension, projectId) {
  const directory = path.join(config.uploadDir, String(projectId));
  fs.mkdirSync(directory, { recursive: true });
  const storedName = `${crypto.randomUUID()}${extension}`;
  const absolutePath = path.join(directory, storedName);
  const buffer = Buffer.from(await file.arrayBuffer());
  fs.writeFileSync(absolutePath, buffer, { flag: 'wx' });
  return {
    absolutePath,
    relativePath: path.posix.join(String(projectId), storedName),
    size: buffer.length,
    hash: sha256Buffer(buffer),
  };
}

function resolvePileIds(db, projectId, pileText) {
  if (!pileText) return [];
  const pileNumbers = [...new Set(pileText.split(/[,，、\s]+/).map((item) => item.trim()).filter(Boolean))];
  const rows = pileNumbers.map((pileNo) => {
    const pile = db.prepare(`
      SELECT pile_id
      FROM piles
      WHERE project_id = ? AND pile_no = ?
    `).get(projectId, pileNo);
    if (!pile) throw new HttpError(400, `桩号不存在：${pileNo}`, 'PILE_NOT_FOUND');
    return Number(pile.pile_id);
  });
  return rows;
}

function makeDocNo(db, projectId, projectCode, docCode) {
  const count = Number(db.prepare(`
    SELECT COUNT(*) AS count
    FROM documents d
    JOIN doc_types dt ON dt.doc_type_id = d.doc_type_id
    WHERE d.project_id = ? AND dt.doc_code = ?
  `).get(projectId, docCode).count);
  return `${projectCode}-${docCode}-${String(count + 1).padStart(3, '0')}`;
}

export async function createDocument(db, session, projectId, docTypeId, formData) {
  const { project, access } = requireProjectAccess(db, session.user_id, projectId);
  if (!canUploadDocType(db, session.user_id, projectId, docTypeId)) {
    throw new HttpError(403, '当前单位无权上传该类文档', 'UPLOAD_FORBIDDEN');
  }

  const docType = db.prepare(`
    SELECT dt.*, u.unit_name AS responsible_unit_name
    FROM doc_types dt
    JOIN project_phases pp ON pp.phase_id = dt.phase_id
    JOIN units u ON u.unit_id = dt.responsible_unit_id
    WHERE dt.doc_type_id = ? AND pp.project_id = ?
  `).get(docTypeId, projectId);
  if (!docType) throw new HttpError(404, '文档类型不存在', 'DOC_TYPE_NOT_FOUND');

  const title = stringField(formData, 'title', 200) || docType.doc_name;
  const docNoInput = stringField(formData, 'doc_no', 100);
  const changeLog = stringField(formData, 'change_log', 1000) || '首次上传';
  const pileText = stringField(formData, 'pile_numbers', 1000);
  const { file, extension } = getUploadedFile(formData);
  const stored = await storeFile(file, extension, projectId);

  try {
    const documentId = inTransaction(db, () => {
      const docNo = docNoInput || makeDocNo(db, projectId, project.project_code, docType.doc_code);
      const status = docType.need_approval ? '待审核' : '已通过';
      const documentResult = db.prepare(`
        INSERT INTO documents (
          doc_type_id, project_id, doc_no, title, current_version, status,
          uploader_id, unit_id, latest_file_path, file_hash
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
      `).run(
        docTypeId,
        projectId,
        docNo,
        title,
        status,
        session.user_id,
        docType.responsible_unit_id,
        stored.relativePath,
        stored.hash,
      );
      const documentId = Number(documentResult.lastInsertRowid);

      const versionResult = db.prepare(`
        INSERT INTO document_versions (
          doc_id, version_no, file_name, file_path, file_size, mime_type,
          file_hash, uploader_id, change_log
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        documentId,
        file.name,
        stored.relativePath,
        stored.size,
        file.type || 'application/octet-stream',
        stored.hash,
        session.user_id,
        changeLog,
      );
      const versionId = Number(versionResult.lastInsertRowid);

      if (docType.need_approval) {
        db.prepare(`
          INSERT INTO approval_flows (
            doc_id, version_id, role, action, status
          ) VALUES (?, ?, '资料审核', '待审批', '待处理')
        `).run(documentId, versionId);
      }

      for (const pileId of resolvePileIds(db, projectId, pileText)) {
        db.prepare(`
          INSERT OR IGNORE INTO document_piles (doc_id, pile_id)
          VALUES (?, ?)
        `).run(documentId, pileId);
      }

      writeAuditLog(db, {
        userId: session.user_id,
        projectId,
        action: '上传文档',
        entityType: 'DOCUMENT',
        entityId: documentId,
        details: {
          doc_no: docNo,
          title,
          file_name: file.name,
          version: 1,
          unit: docType.responsible_unit_name,
          is_admin_override: access.isAdmin,
        },
      });

      return documentId;
    });

    return { document_id: documentId };
  } catch (error) {
    fs.rmSync(stored.absolutePath, { force: true });
    throw error;
  }
}

export async function addDocumentVersion(db, session, projectId, documentId, formData) {
  requireProjectAccess(db, session.user_id, projectId);
  const document = db.prepare(`
    SELECT d.*, dt.doc_code, dt.responsible_unit_id, dt.need_approval,
           u.unit_name AS responsible_unit_name
    FROM documents d
    JOIN doc_types dt ON dt.doc_type_id = d.doc_type_id
    JOIN units u ON u.unit_id = dt.responsible_unit_id
    WHERE d.doc_id = ? AND d.project_id = ?
  `).get(documentId, projectId);
  if (!document) throw new HttpError(404, '文档不存在', 'DOCUMENT_NOT_FOUND');
  if (!canUploadDocType(db, session.user_id, projectId, Number(document.doc_type_id))) {
    throw new HttpError(403, '当前单位无权上传该文档的新版本', 'UPLOAD_FORBIDDEN');
  }

  const changeLog = stringField(formData, 'change_log', 1000) || '上传新版本';
  const pileText = stringField(formData, 'pile_numbers', 1000);
  const { file, extension } = getUploadedFile(formData);
  const stored = await storeFile(file, extension, projectId);

  try {
    const versionNo = inTransaction(db, () => {
      const nextVersion = Number(document.current_version) + 1;
      const status = document.need_approval ? '待审核' : '已通过';
      const versionResult = db.prepare(`
        INSERT INTO document_versions (
          doc_id, version_no, file_name, file_path, file_size, mime_type,
          file_hash, uploader_id, change_log
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        documentId,
        nextVersion,
        file.name,
        stored.relativePath,
        stored.size,
        file.type || 'application/octet-stream',
        stored.hash,
        session.user_id,
        changeLog,
      );
      const versionId = Number(versionResult.lastInsertRowid);

      db.prepare(`
        UPDATE documents
        SET current_version = ?, status = ?, latest_file_path = ?, file_hash = ?,
            uploader_id = ?, unit_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE doc_id = ?
      `).run(
        nextVersion,
        status,
        stored.relativePath,
        stored.hash,
        session.user_id,
        document.responsible_unit_id,
        documentId,
      );

      if (document.need_approval) {
        db.prepare(`
          INSERT INTO approval_flows (
            doc_id, version_id, role, action, status
          ) VALUES (?, ?, '资料审核', '待审批', '待处理')
        `).run(documentId, versionId);
      }

      for (const pileId of resolvePileIds(db, projectId, pileText)) {
        db.prepare(`
          INSERT OR IGNORE INTO document_piles (doc_id, pile_id)
          VALUES (?, ?)
        `).run(documentId, pileId);
      }

      writeAuditLog(db, {
        userId: session.user_id,
        projectId,
        action: '上传文档新版本',
        entityType: 'DOCUMENT_VERSION',
        entityId: versionId,
        details: {
          document_id: documentId,
          doc_no: document.doc_no,
          file_name: file.name,
          version: nextVersion,
          unit: document.responsible_unit_name,
        },
      });

      return nextVersion;
    });

    return { document_id: documentId, version_no: versionNo };
  } catch (error) {
    fs.rmSync(stored.absolutePath, { force: true });
    throw error;
  }
}

export function getVersionFile(db, userId, versionId) {
  const version = db.prepare(`
    SELECT
      dv.version_id, dv.file_name, dv.file_path, dv.file_size, dv.mime_type,
      dv.file_hash, d.project_id
    FROM document_versions dv
    JOIN documents d ON d.doc_id = dv.doc_id
    WHERE dv.version_id = ?
  `).get(versionId);
  if (!version) throw new HttpError(404, '文件不存在', 'FILE_NOT_FOUND');
  requireProjectAccess(db, userId, Number(version.project_id));
  return {
    ...version,
    version_id: Number(version.version_id),
    file_size: Number(version.file_size),
    absolute_path: path.join(config.uploadDir, version.file_path),
  };
}
