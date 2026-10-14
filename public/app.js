const authView = document.querySelector('#authView');
const appView = document.querySelector('#appView');
const mainContent = document.querySelector('#mainContent');
const phaseNav = document.querySelector('#phaseNav');
const modalRoot = document.querySelector('#modalRoot');
const toastRoot = document.querySelector('#toastRoot');
const loginForm = document.querySelector('#loginForm');
const loginError = document.querySelector('#loginError');
const sidebar = document.querySelector('#sidebar');

const state = {
  me: null,
  projectId: null,
  dashboard: null,
  currentPhaseId: null,
  phaseData: null,
  csrfToken: null,
};

class ApiError extends Error {
  constructor(status, message, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;',
  })[character]);
}

function formatDate(value, withTime = true) {
  if (!value) return '—';
  let normalized = String(value);
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(normalized)) {
    normalized = `${normalized.replace(' ', 'T')}Z`;
  }
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
  }).format(date);
}

function formatSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function statusClass(status) {
  if (['已通过', '已完成', '启用'].includes(status)) return 'success';
  if (['待审核', '进行中', '待处理', '待施工'].includes(status)) return 'warning';
  if (['已驳回', '异常'].includes(status)) return 'danger';
  if (['已上传'].includes(status)) return 'teal';
  return 'neutral';
}

function initials(name) {
  return String(name || '用').trim().slice(0, 1) || '用';
}

async function api(path, options = {}) {
  const request = {
    method: options.method || 'GET',
    headers: new Headers(options.headers || {}),
    credentials: 'same-origin',
  };

  if (options.body !== undefined) {
    if (options.body instanceof FormData) {
      request.body = options.body;
    } else if (typeof options.body === 'string') {
      request.body = options.body;
    } else {
      request.headers.set('Content-Type', 'application/json');
      request.body = JSON.stringify(options.body);
    }
  }

  const response = await fetch(path, request);
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    if (response.status === 401 && !path.endsWith('/auth/login')) {
      showLogin();
    }
    throw new ApiError(response.status, payload?.error || '请求失败', payload?.code || 'REQUEST_FAILED');
  }
  return payload;
}

function showToast(message, type = '') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`.trim();
  toast.textContent = message;
  toastRoot.append(toast);
  window.setTimeout(() => toast.remove(), 4000);
}

function showLogin() {
  state.me = null;
  state.dashboard = null;
  state.currentPhaseId = null;
  state.phaseData = null;
  state.projectId = null;
  state.csrfToken = null;
  authView.hidden = false;
  appView.hidden = true;
  closeModal();
}

function showApp() {
  authView.hidden = true;
  appView.hidden = false;
}

async function boot() {
  try {
    const me = await api('/api/me');
    await activateWorkspace(me);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) {
      showToast(error.message || '平台初始化失败', 'error');
    }
    showLogin();
  }
}

async function activateWorkspace(me) {
  state.me = me;
  state.csrfToken = me.csrf_token;
  updateProfile();
  populateProjects(me.projects);
  showApp();

  if (!me.projects.length) {
    mainContent.innerHTML = `
      <div class="empty-state">
        <h2>暂无项目权限</h2>
        <p>当前账号尚未被分配到任何项目，请联系系统管理员。</p>
      </div>`;
    phaseNav.innerHTML = '';
    return;
  }

  state.projectId = Number(me.projects[0].project_id);
  document.querySelector('#projectSelect').value = String(state.projectId);
  await loadWorkspace();
}

function populateProjects(projects) {
  const select = document.querySelector('#projectSelect');
  select.innerHTML = projects.map((project) => `
    <option value="${Number(project.project_id)}">${escapeHtml(project.project_name)}</option>
  `).join('');
}

function updateProfile() {
  const user = state.me?.user;
  if (!user) return;
  document.querySelector('#userName').textContent = user.real_name || user.username;
  document.querySelector('#userUnit').textContent = user.unit_name || '系统管理';
  document.querySelector('#userAvatar').textContent = initials(user.real_name || user.username);
  document.querySelector('#projectMeta').textContent = state.dashboard
    ? `${state.dashboard.project.project_code} · ${state.dashboard.project.project_name}`
    : '项目加载中';

  const roles = state.dashboard?.access?.roles || state.me?.projects?.[0]?.roles || [];
  document.querySelector('#profileRoleList').innerHTML = roles.length
    ? roles.map((item) => `
        <div class="role-line">
          <strong>${escapeHtml(item.role)}</strong>
          ${escapeHtml(item.unit_name || '系统管理')}
        </div>`).join('')
    : '<div class="role-line">暂无项目角色</div>';
}

async function loadWorkspace() {
  mainContent.innerHTML = '<div class="loading-state"><span class="spinner"></span>正在加载项目数据…</div>';
  try {
    state.dashboard = await api(`/api/projects/${state.projectId}/dashboard`);
    state.currentPhaseId = null;
    state.phaseData = null;
    updateProfile();
    renderNavigation();
    renderDashboard();
  } catch (error) {
    mainContent.innerHTML = `<div class="empty-state"><h2>项目加载失败</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function renderNavigation() {
  const dashboard = state.dashboard;
  if (!dashboard) return;
  const overviewActive = state.currentPhaseId === null;
  const items = [
    `<button class="nav-item ${overviewActive ? 'active' : ''}" type="button" data-action="dashboard">
      <span class="nav-index">⌂</span>
      <span class="nav-copy"><strong>项目总览</strong><small>进度与预警</small></span>
      <span class="nav-percent">${dashboard.summary.completionPercent}%</span>
    </button>`,
  ];

  for (const phase of dashboard.phases) {
    items.push(`
      <button class="nav-item ${Number(phase.phase_id) === state.currentPhaseId ? 'active' : ''}" type="button"
        data-action="open-phase" data-phase="${Number(phase.phase_id)}">
        <span class="nav-index">${Number(phase.phase_order)}</span>
        <span class="nav-copy">
          <strong>${escapeHtml(phase.phase_name)}</strong>
          <small>${phase.covered_count}/${phase.required_count} 类已归档</small>
        </span>
        <span class="nav-percent">${phase.completion_percent}%</span>
      </button>`);
  }
  phaseNav.innerHTML = items.join('');
}

function renderDashboard() {
  const dashboard = state.dashboard;
  if (!dashboard) return;
  const summary = dashboard.summary;
  const construction = dashboard.phases.find((phase) => Number(phase.phase_order) === 5);
  const roles = dashboard.access.roles || [];
  const unitNames = [...new Set(roles.map((item) => item.unit_name || '系统管理'))].join('、');

  mainContent.innerHTML = `
    <div class="page-heading">
      <div>
        <div class="badge teal">${escapeHtml(dashboard.project.status)}</div>
        <h1>${escapeHtml(dashboard.project.project_name)}</h1>
        <p>${escapeHtml(dashboard.project.project_code)} · ${escapeHtml(dashboard.project.location || '项目地点待补充')}</p>
      </div>
      <div class="heading-actions">
        ${construction ? `<button class="button primary" type="button" data-action="open-phase" data-phase="${construction.phase_id}">进入桩基施工阶段 →</button>` : ''}
      </div>
    </div>

    <section class="kpi-grid">
      <article class="kpi-card accent">
        <div class="kpi-label">全过程文档完成度</div>
        <div class="kpi-value">${summary.completionPercent}<small>%</small></div>
        <div class="progress-track"><span style="width:${summary.completionPercent}%"></span></div>
        <div class="kpi-note">${summary.coveredCount} / ${summary.requiredCount} 类必传文档已有文件</div>
      </article>
      <article class="kpi-card">
        <div class="kpi-label">已归档文档</div>
        <div class="kpi-value">${summary.documentCount}<small>份</small></div>
        <div class="kpi-note">版本化保存，历史版本不被覆盖</div>
      </article>
      <article class="kpi-card">
        <div class="kpi-label">待审核</div>
        <div class="kpi-value">${summary.pendingApprovals}<small>份</small></div>
        <div class="kpi-note">审批流模块已进入数据模型</div>
      </article>
      <article class="kpi-card">
        <div class="kpi-label">质量预警</div>
        <div class="kpi-value">${summary.alertCount}<small>项</small></div>
        <div class="kpi-note">缺项、超期与异常数据后续自动触发</div>
      </article>
    </section>

    <section class="dashboard-grid">
      <article class="panel">
        <div class="panel-header">
          <div><h2>七个阶段进度</h2><p>文档流驱动业务流，点击阶段进入文档台账</p></div>
          <span class="badge neutral">${dashboard.phases.length} 个阶段</span>
        </div>
        <div class="panel-body phase-list">
          ${dashboard.phases.map(renderPhaseRow).join('')}
        </div>
      </article>

      <div style="display:grid;gap:16px">
        <article class="panel">
          <div class="panel-header">
            <div><h2>当前访问身份</h2><p>${escapeHtml(unitNames || '未分配单位')}</p></div>
            <span class="badge ${dashboard.access.isAdmin ? 'danger' : 'success'}">${dashboard.access.isAdmin ? '管理权限' : '受控权限'}</span>
          </div>
          <div class="panel-body">
            <div class="permission-banner" style="margin-top:0">
              <div>
                <strong>${dashboard.access.isAdmin ? '管理员可跨单位维护文档' : '仅责任单位可上传'}</strong>
                <p>${dashboard.access.isAdmin ? '管理员操作仍会写入审计日志。' : '你只能上传本单位负责的文档类型，其他资料均以只读方式查看。'}</p>
              </div>
            </div>
          </div>
        </article>

        <article class="panel">
          <div class="panel-header"><div><h2>最近上传</h2><p>按最后更新时间排序</p></div></div>
          <div class="panel-body recent-list">
            ${dashboard.recentDocuments.length
              ? dashboard.recentDocuments.map(renderRecentDocument).join('')
              : '<div class="empty-state">尚无上传记录，从“桩基施工阶段”开始录入。</div>'}
          </div>
        </article>
      </div>
    </section>
  `;
}

function renderPhaseRow(phase) {
  return `
    <button class="phase-row ${Number(phase.phase_order) === 5 ? 'highlight' : ''}" type="button"
      data-action="open-phase" data-phase="${Number(phase.phase_id)}">
      <span class="phase-number">${Number(phase.phase_order)}</span>
      <span class="phase-info">
        <strong>${escapeHtml(phase.phase_name)}</strong>
        <small>${phase.document_count} 份文档 · ${phase.covered_count}/${phase.required_count} 类已覆盖</small>
      </span>
      <span class="mini-progress"><span style="width:${phase.completion_percent}%"></span></span>
      <span class="phase-percent">${phase.completion_percent}%</span>
    </button>`;
}

function renderRecentDocument(document) {
  return `
    <button class="recent-item" type="button" data-action="open-document" data-document="${Number(document.doc_id)}">
      <span>
        <strong>${escapeHtml(document.title)}</strong>
        <small>${escapeHtml(document.unit_name || document.upload_unit_name || '')} · ${escapeHtml(document.doc_type_name)}</small>
      </span>
      <span class="badge ${statusClass(document.status)}">v${Number(document.current_version)}</span>
    </button>`;
}

async function openPhase(phaseId) {
  state.currentPhaseId = Number(phaseId);
  state.phaseData = null;
  renderNavigation();
  mainContent.innerHTML = '<div class="loading-state"><span class="spinner"></span>正在加载阶段台账…</div>';
  try {
    state.phaseData = await api(`/api/projects/${state.projectId}/phases/${state.currentPhaseId}`);
    renderPhase();
  } catch (error) {
    mainContent.innerHTML = `<div class="empty-state"><h2>阶段加载失败</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function renderPhase() {
  const data = state.phaseData;
  if (!data) return;
  const allTypes = data.groups.flatMap((group) => group.doc_types);
  const uploadableCount = allTypes.filter((item) => item.can_upload).length;
  const roleNames = data.access.roles.map((item) => `${item.unit_name || '系统管理'} · ${item.role}`).join('；');

  mainContent.innerHTML = `
    <div class="phase-hero">
      <div>
        <span class="badge ${statusClass(data.phase.status)}">${escapeHtml(data.phase.status)}</span>
        <h1>${escapeHtml(data.phase.phase_name)}</h1>
        <p>阶段 ${Number(data.phase.phase_order)} / 7 · 文档类型按责任单位自动分区，所有上传均保留版本与审计记录。</p>
      </div>
      <div class="hero-progress">
        <div class="hero-progress-number">
          <strong>${data.progress.completion_percent}%</strong>
          <span>${data.progress.covered} / ${data.progress.required} 类</span>
        </div>
        <div class="progress-track"><span style="width:${data.progress.completion_percent}%"></span></div>
        <small>必传文档类型覆盖率</small>
      </div>
    </div>

    <div class="permission-banner">
      <div>
        <strong>${data.access.isAdmin ? '管理员模式：可跨单位上传' : `你的权限：可上传 ${uploadableCount} 类，其余只读`}</strong>
        <p>${escapeHtml(roleNames || '暂无项目角色')}。权限由“文档类型责任单位 + 项目角色”共同判定，API 后端同步强制校验。</p>
      </div>
      <code>READ &amp; APPEND ONLY</code>
    </div>

    ${data.groups.map(renderUnitGroup).join('')}
  `;
}

function renderUnitGroup(group) {
  const covered = group.doc_types.filter((item) => item.document_count > 0).length;
  return `
    <section class="unit-section">
      <div class="unit-header">
        <div class="unit-title">
          <span class="unit-dot"></span>
          <h2>${escapeHtml(group.responsible_unit_name)}</h2>
          <span>${group.doc_types.length} 类文档 · ${covered} 类已上传</span>
        </div>
      </div>
      <div class="doc-grid">
        ${group.doc_types.map(renderDocTypeCard).join('')}
      </div>
    </section>`;
}

function renderDocTypeCard(type) {
  const uploaded = Number(type.document_count) > 0;
  const latest = type.documents[0];
  return `
    <article class="doc-card ${type.can_upload ? 'can-upload' : 'pending'}">
      <div class="doc-topline">
        <span class="doc-code">${escapeHtml(type.doc_code)}</span>
        <span class="badge ${uploaded ? 'success' : (type.is_required ? 'warning' : 'neutral')}">
          ${uploaded ? `已上传 ${type.document_count} 份` : (type.is_required ? '待上传' : '待补充')}
        </span>
      </div>
      <h3>${escapeHtml(type.doc_name)}</h3>
      <div class="doc-meta">
        <span class="meta-chip">${escapeHtml(type.file_formats || '未指定格式')}</span>
        <span class="meta-chip">${type.need_approval ? '需审核' : '上传即归档'}</span>
        <span class="meta-chip">${escapeHtml(type.responsible_unit_name)}</span>
      </div>
      <div class="doc-summary">
        ${uploaded
          ? `最近更新：<strong>${formatDate(latest.updated_at)}</strong><br>${escapeHtml(latest.uploader_name || '')} · ${escapeHtml(latest.upload_unit_name || type.responsible_unit_name)}`
          : escapeHtml(type.description || '责任单位上传后，其他参建单位可查看。')}
      </div>
      ${type.documents.length ? `
        <div class="document-list">
          ${type.documents.slice(0, 2).map((document) => `
            <button class="document-link" type="button" data-action="open-document" data-document="${Number(document.doc_id)}">
              <span>${escapeHtml(document.title)}</span>
              <small>v${Number(document.current_version)}</small>
            </button>`).join('')}
          ${type.documents.length > 2 ? `<span class="meta-chip">另有 ${type.documents.length - 2} 份文档</span>` : ''}
        </div>` : ''}
      <div class="doc-actions">
        ${type.can_upload
          ? `<button class="button primary" type="button" data-action="upload-doc-type" data-type="${Number(type.doc_type_id)}">${uploaded ? '追加文档' : '上传文件'}</button>`
          : '<span class="readonly-note"><span class="lock-icon">▣</span>仅责任单位可上传</span>'}
        ${latest ? `<button class="button ghost" type="button" data-action="open-document" data-document="${Number(latest.doc_id)}">查看 ${type.document_count} 份</button>` : ''}
      </div>
    </article>`;
}

function openUploadModal(typeId) {
  const type = state.phaseData?.groups
    .flatMap((group) => group.doc_types)
    .find((item) => Number(item.doc_type_id) === Number(typeId));
  if (!type) return;

  showModal(`
    <div class="modal">
      <div class="modal-header">
        <div>
          <h2>上传文档</h2>
          <p>${escapeHtml(type.doc_code)} · ${escapeHtml(type.doc_name)}</p>
        </div>
        <button class="modal-close" type="button" data-action="close-modal" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <form id="uploadForm" class="upload-form" data-type="${Number(type.doc_type_id)}">
          <div class="alert info">
            文档责任单位为 <strong>${escapeHtml(type.responsible_unit_name)}</strong>。上传后将生成 v1.0 版本；后续更新只能追加版本，不能覆盖历史文件。
          </div>
          <div class="form-field">
            <label for="uploadTitle">文档标题</label>
            <input id="uploadTitle" name="title" maxlength="200" value="${escapeHtml(type.doc_name)}" required>
          </div>
          <div class="form-row">
            <div class="form-field">
              <label for="uploadDocNo">文档编号（可选）</label>
              <input id="uploadDocNo" name="doc_no" maxlength="100" placeholder="留空由平台自动编号">
            </div>
            <div class="form-field">
              <label for="uploadPiles">关联桩号（可选）</label>
              <input id="uploadPiles" name="pile_numbers" placeholder="如 ZH-001, ZH-002">
              <small>多个桩号用逗号、顿号或空格分隔。</small>
            </div>
          </div>
          <div class="form-field">
            <label>文件</label>
            <label class="file-drop">
              <input id="uploadFile" name="file" type="file" required
                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.dwg,.dxf,.rvt,.ifc,.jpg,.jpeg,.png,.webp,.tif,.tiff,.mp4,.mov,.avi,.mkv,.zip,.rar,.7z">
              <span><strong>点击选择文件</strong><span>支持报告、图纸、模型、照片、视频与压缩包，单个文件不超过 200 MB</span><span id="uploadFileName" class="file-name"></span></span>
            </label>
          </div>
          <div class="form-field">
            <label for="uploadChangeLog">上传说明</label>
            <textarea id="uploadChangeLog" name="change_log" maxlength="1000" placeholder="说明本次上传内容，例如：首版施工记录"></textarea>
          </div>
          <p id="uploadError" class="form-error"></p>
          <div class="modal-actions">
            <button class="button ghost" type="button" data-action="close-modal">取消</button>
            <button class="button primary" type="submit">确认上传</button>
          </div>
        </form>
      </div>
    </div>`);

  const form = modalRoot.querySelector('#uploadForm');
  form.elements.file.addEventListener('change', () => {
    const fileName = form.elements.file.files[0]?.name || '';
    modalRoot.querySelector('#uploadFileName').textContent = fileName;
  });
  form.addEventListener('submit', handleCreateDocument);
}

async function handleCreateDocument(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('[type="submit"]');
  const errorNode = form.querySelector('#uploadError');
  submit.disabled = true;
  submit.textContent = '上传中…';
  errorNode.textContent = '';

  try {
    await api(`/api/projects/${state.projectId}/document-types/${form.dataset.type}/documents`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': state.csrfToken },
      body: new FormData(form),
    });
    closeModal();
    await refreshWorkspace();
    showToast('文档上传成功，已生成第一个版本。', 'success');
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.textContent = '确认上传';
  }
}

async function openDocumentModal(documentId) {
  showModal('<div class="loading-state" style="min-height:320px"><span class="spinner"></span>正在加载文档版本…</div>');
  try {
    const data = await api(`/api/projects/${state.projectId}/documents/${documentId}`);
    renderDocumentModal(data);
  } catch (error) {
    closeModal();
    showToast(error.message, 'error');
  }
}

function renderDocumentModal(data) {
  const document = data.document;
  const canUpload = data.can_upload;
  const latest = data.versions[0];
  showModal(`
    <div class="modal wide">
      <div class="modal-header">
        <div>
          <h2>${escapeHtml(document.title)}</h2>
          <p>${escapeHtml(document.doc_no)} · ${escapeHtml(document.doc_type_name)}</p>
        </div>
        <button class="modal-close" type="button" data-action="close-modal" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <div class="document-detail-head">
          <div>
            <span class="badge ${statusClass(document.status)}">${escapeHtml(document.status)}</span>
            <div class="meta-grid">
              <div class="meta-block"><span>当前版本</span><strong>v${Number(document.current_version)}</strong></div>
              <div class="meta-block"><span>责任单位</span><strong>${escapeHtml(document.responsible_unit_name)}</strong></div>
              <div class="meta-block"><span>上传单位</span><strong>${escapeHtml(document.upload_unit_name || document.responsible_unit_name)}</strong></div>
              <div class="meta-block"><span>首次上传</span><strong>${formatDate(document.created_at)}</strong></div>
              <div class="meta-block"><span>最后更新</span><strong>${formatDate(document.updated_at)}</strong></div>
              <div class="meta-block"><span>审批要求</span><strong>${document.need_approval ? '需要审核' : '无需审核'}</strong></div>
            </div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end">
            ${latest ? `<a class="button ghost" href="/api/files/${latest.version_id}?download=1">下载最新版</a>` : ''}
            ${canUpload ? `<button class="button primary" type="button" data-action="version-document" data-document="${Number(document.doc_id)}">上传新版本</button>` : ''}
          </div>
        </div>

        ${!canUpload ? '<div class="alert info" style="margin-top:18px">当前单位对该文档只有查看和下载权限，不能新增版本或修改内容。</div>' : ''}

        <div class="section-title">
          <h3>版本历史</h3>
          <span class="badge neutral">${data.versions.length} 个版本</span>
        </div>
        <div class="version-list">
          ${data.versions.map((version) => `
            <div class="version-row">
              <span class="version-badge">v${Number(version.version_no)}</span>
              <div class="version-info">
                <strong>${escapeHtml(version.file_name)}</strong>
                <small>${escapeHtml(version.uploader_name)} · ${formatDate(version.uploaded_at)} · ${formatSize(version.file_size)} · ${escapeHtml(version.change_log || '')}</small>
                <small>SHA-256 ${escapeHtml(String(version.file_hash).slice(0, 16))}…</small>
              </div>
              <div class="version-actions">
                <a href="/api/files/${Number(version.version_id)}" target="_blank" rel="noopener">预览</a>
                <a href="/api/files/${Number(version.version_id)}?download=1">下载</a>
              </div>
            </div>`).join('')}
        </div>

        ${data.piles.length ? `
          <div class="section-title"><h3>关联桩位</h3></div>
          <div class="doc-meta">${data.piles.map((pile) => `<span class="meta-chip">${escapeHtml(pile.pile_no)} · ${escapeHtml(pile.status)}</span>`).join('')}</div>` : ''}

        ${data.approvals.length ? `
          <div class="section-title"><h3>审批记录</h3></div>
          <div class="version-list">
            ${data.approvals.map((approval) => `
              <div class="version-row">
                <span class="version-badge">审</span>
                <div class="version-info">
                  <strong>${escapeHtml(approval.action)} · ${escapeHtml(approval.status)}</strong>
                  <small>${escapeHtml(approval.role || '')} · ${escapeHtml(approval.approver_name || '待指派审批人')} · ${formatDate(approval.created_at)}</small>
                </div>
              </div>`).join('')}
          </div>` : ''}
      </div>
    </div>`);
}

function openVersionModal(documentId) {
  showModal(`
    <div class="modal">
      <div class="modal-header">
        <div><h2>上传新版本</h2><p>历史版本将永久保留，新版本成为当前版本。</p></div>
        <button class="modal-close" type="button" data-action="close-modal" aria-label="关闭">×</button>
      </div>
      <div class="modal-body">
        <form id="versionForm" class="upload-form" data-document="${Number(documentId)}">
          <div class="form-field">
            <label>文件</label>
            <label class="file-drop">
              <input id="versionFile" name="file" type="file" required
                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.dwg,.dxf,.rvt,.ifc,.jpg,.jpeg,.png,.webp,.tif,.tiff,.mp4,.mov,.avi,.mkv,.zip,.rar,.7z">
              <span><strong>点击选择新版本文件</strong><span>单个文件不超过 200 MB</span><span id="versionFileName" class="file-name"></span></span>
            </label>
          </div>
          <div class="form-field">
            <label for="versionPiles">关联桩号（可选）</label>
            <input id="versionPiles" name="pile_numbers" placeholder="如 ZH-001, ZH-002">
          </div>
          <div class="form-field">
            <label for="versionChangeLog">版本说明</label>
            <textarea id="versionChangeLog" name="change_log" maxlength="1000" placeholder="说明本版本新增或修正的内容" required></textarea>
          </div>
          <p id="versionError" class="form-error"></p>
          <div class="modal-actions">
            <button class="button ghost" type="button" data-action="close-modal">取消</button>
            <button class="button primary" type="submit">上传新版本</button>
          </div>
        </form>
      </div>
    </div>`);

  const form = modalRoot.querySelector('#versionForm');
  form.elements.file.addEventListener('change', () => {
    modalRoot.querySelector('#versionFileName').textContent = form.elements.file.files[0]?.name || '';
  });
  form.addEventListener('submit', handleVersionUpload);
}

async function handleVersionUpload(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('[type="submit"]');
  const errorNode = form.querySelector('#versionError');
  submit.disabled = true;
  submit.textContent = '上传中…';
  errorNode.textContent = '';

  try {
    await api(`/api/projects/${state.projectId}/documents/${form.dataset.document}/versions`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': state.csrfToken },
      body: new FormData(form),
    });
    closeModal();
    await refreshWorkspace();
    showToast('新版本上传成功。', 'success');
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    submit.disabled = false;
    submit.textContent = '上传新版本';
  }
}

async function refreshWorkspace() {
  state.dashboard = await api(`/api/projects/${state.projectId}/dashboard`);
  updateProfile();
  if (state.currentPhaseId) {
    state.phaseData = await api(`/api/projects/${state.projectId}/phases/${state.currentPhaseId}`);
    renderNavigation();
    renderPhase();
  } else {
    renderNavigation();
    renderDashboard();
  }
}

function showModal(html) {
  modalRoot.innerHTML = html;
  modalRoot.hidden = false;
  document.body.style.overflow = 'hidden';
}

function closeModal() {
  modalRoot.hidden = true;
  modalRoot.innerHTML = '';
  document.body.style.overflow = '';
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = loginForm.querySelector('[type="submit"]');
  submit.disabled = true;
  loginError.textContent = '';
  try {
    const me = await api('/api/auth/login', {
      method: 'POST',
      body: {
        username: document.querySelector('#username').value.trim(),
        password: document.querySelector('#password').value,
      },
    });
    await activateWorkspace(me);
  } catch (error) {
    loginError.textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector('#demoAccounts').addEventListener('click', (event) => {
  const button = event.target.closest('[data-user]');
  if (!button) return;
  document.querySelector('#username').value = button.dataset.user;
  document.querySelector('#password').focus();
});

phaseNav.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  if (button.dataset.action === 'dashboard') {
    state.currentPhaseId = null;
    state.phaseData = null;
    renderNavigation();
    renderDashboard();
  }
  if (button.dataset.action === 'open-phase') openPhase(button.dataset.phase);
  sidebar.classList.remove('open');
});

mainContent.addEventListener('click', (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'open-phase') openPhase(button.dataset.phase);
  if (action === 'upload-doc-type') openUploadModal(button.dataset.type);
  if (action === 'open-document') openDocumentModal(button.dataset.document);
});

modalRoot.addEventListener('click', (event) => {
  const actionTarget = event.target.closest('[data-action]');
  if (event.target === modalRoot || actionTarget?.dataset.action === 'close-modal') {
    closeModal();
    return;
  }
  if (actionTarget?.dataset.action === 'version-document') {
    openVersionModal(actionTarget.dataset.document);
  }
});

document.querySelector('#projectSelect').addEventListener('change', async (event) => {
  state.projectId = Number(event.target.value);
  await loadWorkspace();
});

document.querySelector('#profileButton').addEventListener('click', () => {
  const menu = document.querySelector('#profileMenu');
  menu.hidden = !menu.hidden;
});

document.querySelector('#logoutButton').addEventListener('click', async () => {
  try {
    await api('/api/auth/logout', {
      method: 'POST',
      headers: { 'X-CSRF-Token': state.csrfToken },
      body: {},
    });
  } catch {
    // The local state is cleared even if the server session has already expired.
  }
  showLogin();
});

document.querySelector('#mobileMenuButton').addEventListener('click', () => {
  sidebar.classList.toggle('open');
});

document.addEventListener('click', (event) => {
  const menu = document.querySelector('#profileMenu');
  if (!menu || menu.hidden) return;
  if (!event.target.closest('#profileButton') && !event.target.closest('#profileMenu')) {
    menu.hidden = true;
  }
});

boot();
