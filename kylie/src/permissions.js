const UPLOAD_ROLES = new Set(['系统管理员', '项目经理', '单位管理员', '资料员']);

export function getUserProjectAccess(db, userId, projectId) {
  const user = db.prepare(`
    SELECT user_id, username, real_name, status, unit_id
    FROM users
    WHERE user_id = ?
  `).get(userId);

  if (!user || user.status !== '启用') {
    return { user: null, isAdmin: false, hasAccess: false, roles: [], canUpload: false };
  }

  const roles = db.prepare(`
    SELECT upr.role, upr.unit_id, u.unit_name, u.unit_code
    FROM user_project_roles upr
    LEFT JOIN units u ON u.unit_id = upr.unit_id
    WHERE upr.user_id = ? AND upr.project_id = ?
    ORDER BY upr.id
  `).all(userId, projectId);

  const isAdmin = roles.some((item) => item.role === '系统管理员');
  return {
    user,
    isAdmin,
    hasAccess: isAdmin || roles.length > 0,
    roles,
    canUpload: isAdmin || roles.some((item) => UPLOAD_ROLES.has(item.role)),
  };
}

export function canUploadDocType(db, userId, projectId, docTypeId) {
  const access = getUserProjectAccess(db, userId, projectId);
  if (!access.hasAccess) return false;
  if (access.isAdmin) return true;

  const docType = db.prepare(`
    SELECT doc_type_id, responsible_unit_id
    FROM doc_types
    WHERE doc_type_id = ?
  `).get(docTypeId);
  if (!docType) return false;

  return access.roles.some((item) => (
    Number(item.unit_id) === Number(docType.responsible_unit_id)
    && UPLOAD_ROLES.has(item.role)
  ));
}

export function canUploadDocument(db, userId, projectId, documentId) {
  const docType = db.prepare(`
    SELECT doc_type_id
    FROM documents
    WHERE doc_id = ? AND project_id = ?
  `).get(documentId, projectId);
  if (!docType) return false;
  return canUploadDocType(db, userId, projectId, Number(docType.doc_type_id));
}

export function writeAuditLog(db, {
  userId,
  projectId,
  action,
  entityType,
  entityId = null,
  details = null,
  ipAddress = null,
}) {
  db.prepare(`
    INSERT INTO audit_logs (
      user_id, project_id, action, entity_type, entity_id, details, ip_address
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(
    userId,
    projectId,
    action,
    entityType,
    entityId,
    details ? JSON.stringify(details) : null,
    ipAddress,
  );
}
