'use strict';

/* ============ 工具 ============ */
const $ = (sel) => document.querySelector(sel);

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB';
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function toast(msg, isError) {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast' + (isError ? ' error' : '');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), 2600);
}

async function api(url, options) {
  const opts = options || {};
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = Object.assign({ 'Content-Type': 'application/json' }, opts.headers);
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  let data = {};
  try { data = await res.json(); } catch (e) { /* 非 JSON 响应 */ }
  if (!res.ok) throw new Error(data.error || '请求失败');
  return data;
}

/* ============ 全局状态 ============ */
let currentUser = null;
let stages = [];
let currentProject = null;
let currentStageId = null;
let stats = {};

/* ============ 视图切换 ============ */
function showView(name) {
  ['view-login', 'view-workbench', 'view-project'].forEach((id) => {
    $(`#${id}`).classList.toggle('hidden', id !== name);
  });
}

/* ============ 登录 / 注册 ============ */
let authMode = 'login';

function setAuthMode(mode) {
  authMode = mode;
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.mode === mode));
  $('#display-name-field').hidden = mode !== 'register';
  $('#auth-submit').textContent = mode === 'login' ? '登 录' : '注册并登录';
  $('#auth-error').textContent = '';
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = $('#auth-username').value.trim();
  const password = $('#auth-password').value;
  const errEl = $('#auth-error');
  errEl.textContent = '';
  try {
    let data;
    if (authMode === 'login') {
      data = await api('/api/auth/login', { method: 'POST', body: { username, password } });
    } else {
      data = await api('/api/auth/register', {
        method: 'POST',
        body: { username, password, displayName: $('#auth-displayname').value.trim() }
      });
    }
    currentUser = data.user;
    enterWorkbench();
  } catch (err) {
    errEl.textContent = err.message;
  }
}

/* ============ 工作台 ============ */
async function enterWorkbench() {
  showView('view-workbench');
  $('#workbench-username').textContent =
    `${currentUser.displayName || currentUser.username}（${currentUser.username}）`;
  $('#btn-manage-users').hidden = !currentUser.isAdmin;
  await loadProjects();
}

async function loadProjects() {
  try {
    const data = await api('/api/projects');
    const list = data.projects || [];
    $('#project-empty').classList.toggle('hidden', list.length > 0);
    $('#project-grid').innerHTML = list.map(projectCard).join('');
    document.querySelectorAll('.project-card').forEach((card) => {
      card.addEventListener('click', () => openProject(Number(card.dataset.id)));
    });
  } catch (err) {
    toast(err.message, true);
  }
}

function projectCard(p) {
  const desc = p.description ? `<div class="meta">${escapeHtml(p.description)}</div>` : '';
  const loc = p.location ? `<div class="meta loc">${escapeHtml(p.location)}</div>` : '';
  const owner = p.owner_name ? `<div class="meta">负责人：${escapeHtml(p.owner_name)}</div>` : '';
  return `
    <div class="project-card" data-id="${p.id}">
      <h3>${escapeHtml(p.name)}</h3>
      ${owner}${loc}${desc}
      <div class="foot">
        <span>更新于 ${escapeHtml(p.updated_at)}</span>
        <span class="doc-count">进入项目 →</span>
      </div>
    </div>`;
}

/* ============ 项目详情 ============ */
async function openProject(id) {
  try {
    const data = await api(`/api/projects/${id}`);
    currentProject = data.project;
    stats = data.stats || {};
    const stageData = await api('/api/stages');
    stages = stageData.stages || [];
    currentStageId = stages.length ? stages[0].id : null;

    showView('view-project');
    $('#project-title').textContent = currentProject.name;
    renderStageNav();
    renderStageContent();
  } catch (err) {
    toast(err.message, true);
  }
}

function renderStageNav() {
  const nav = $('#stage-nav');
  nav.innerHTML = stages.map((s) => {
    const n = stats[s.id] || 0;
    return `
      <div class="stage-nav-item ${s.id === currentStageId ? 'active' : ''}" data-id="${s.id}">
        <span>${escapeHtml(s.name)}</span>
        <span class="badge">${n}</span>
      </div>`;
  }).join('');
  nav.querySelectorAll('.stage-nav-item').forEach((item) => {
    item.addEventListener('click', () => {
      currentStageId = Number(item.dataset.id);
      renderStageNav();
      renderStageContent();
    });
  });
}

async function renderStageContent() {
  const stage = stages.find((s) => s.id === currentStageId);
  const box = $('#stage-content');
  if (!stage) { box.innerHTML = ''; return; }

  // 空阶段（设计 / 施工，或尚未填写文档类型的阶段）
  if (!stage.parties || stage.parties.length === 0) {
    box.innerHTML = `
      <div class="stage-head">
        <h2>${escapeHtml(stage.name)}</h2>
        <p class="muted">第 ${stage.id} / ${stages.length} 阶段</p>
      </div>
      <div class="stage-empty">
        <div class="empty-icon">📄</div>
        <strong>该阶段文档清单待完善</strong>
        <p>${stage.owner ? '负责人：' + escapeHtml(stage.owner) + '，' : ''}暂未填写文档类型</p>
      </div>`;
    return;
  }

  let docs = [];
  try {
    const data = await api(`/api/projects/${currentProject.id}/documents?stage=${stage.id}`);
    docs = data.documents || [];
  } catch (err) {
    toast(err.message, true);
  }

  box.innerHTML = `
    <div class="stage-head">
      <h2>${escapeHtml(stage.name)}</h2>
      <p class="muted">第 ${stage.id} / ${stages.length} 阶段 · ${stage.parties.length} 个参与单位</p>
    </div>
    ${stage.parties.map((party) => renderParty(party, docs)).join('')}`;

  // 绑定上传按钮
  box.querySelectorAll('.upload-btn').forEach((btn) => {
    btn.addEventListener('click', () => btn.nextElementSibling.click());
  });
  box.querySelectorAll('.file-input').forEach((input) => {
    input.addEventListener('change', () => onUpload(stage, input));
  });
  // 绑定删除按钮
  box.querySelectorAll('.file-item .del').forEach((btn) => {
    btn.addEventListener('click', () => onDeleteDoc(Number(btn.dataset.id)));
  });
}

function renderParty(party, allDocs) {
  const partyDocs = allDocs.filter((d) => d.party === party.name);
  const rows = (party.docs || []).map((doc) => {
    const files = partyDocs.filter((d) => d.doc_type === doc.name);
    return `
      <div class="doc-row">
        <div class="doc-row-head">
          <span class="doc-name">${escapeHtml(doc.name)}</span>
          <span class="type-tag">${escapeHtml(doc.type)}</span>
        </div>
        <div class="file-list">
          ${files.length ? files.map(fileItem).join('') : `<div class="doc-empty-hint">暂无文件</div>`}
        </div>
        <button class="upload-btn" type="button">＋ 上传文件</button>
        <input type="file" class="file-input" hidden multiple
          data-party="${escapeHtml(party.name)}" data-doctype="${escapeHtml(doc.name)}" />
      </div>`;
  }).join('');

  return `
    <div class="party-block">
      <div class="party-head">
        <span class="dot"></span>
        <h3>${escapeHtml(party.name)}</h3>
        <span class="count">${partyDocs.length} 份文件</span>
      </div>
      ${rows || `<div class="doc-row"><div class="doc-empty-hint">该单位暂无文档类型</div></div>`}
    </div>`;
}

function fileItem(d) {
  return `
    <div class="file-item">
      <span class="fname" title="${escapeHtml(d.original_name)}">${escapeHtml(d.original_name)}</span>
      <span class="fsize">${fmtSize(d.file_size)}</span>
      <a href="/api/documents/${d.id}/download" download>下载</a>
      <button class="del" data-id="${d.id}" type="button">删除</button>
    </div>`;
}

async function onUpload(stage, input) {
  const party = input.dataset.party;
  const docType = input.dataset.doctype;
  const files = Array.from(input.files || []);
  if (!files.length) return;

  for (const file of files) {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('stageId', stage.id);
    fd.append('party', party);
    fd.append('docType', docType);
    try {
      await api(`/api/projects/${currentProject.id}/documents`, { method: 'POST', body: fd });
    } catch (err) {
      toast(`「${file.name}」上传失败：${err.message}`, true);
    }
  }
  input.value = '';
  toast('上传完成');
  await refreshStage();
}

async function onDeleteDoc(docId) {
  if (!confirm('确定删除该文档吗？此操作不可恢复。')) return;
  try {
    await api(`/api/documents/${docId}`, { method: 'DELETE' });
    toast('已删除');
    await refreshStage();
  } catch (err) {
    toast(err.message, true);
  }
}

async function refreshStage() {
  // 刷新当前阶段文档列表 + 侧栏数量
  try {
    const data = await api(`/api/projects/${currentProject.id}`);
    stats = data.stats || {};
  } catch (e) { /* ignore */ }
  renderStageNav();
  await renderStageContent();
}

/* ============ 弹窗 ============ */
function openModal(html) {
  $('#modal-box').innerHTML = html;
  $('#modal-overlay').classList.remove('hidden');
}
function closeModal() {
  $('#modal-overlay').classList.add('hidden');
  $('#modal-box').innerHTML = '';
}

/* —— 新建 / 编辑项目 —— */
function openProjectModal(project) {
  const isEdit = !!project;
  openModal(`
    <h3>${isEdit ? '编辑项目' : '新建项目'}</h3>
    <label class="field"><span>项目名称 *</span>
      <input type="text" id="m-name" value="${project ? escapeHtml(project.name) : ''}" placeholder="例如：XX 大厦桩基工程" />
    </label>
    <label class="field"><span>项目地点</span>
      <input type="text" id="m-location" value="${project ? escapeHtml(project.location) : ''}" placeholder="例如：上海市浦东新区" />
    </label>
    <label class="field"><span>项目描述</span>
      <textarea id="m-desc" placeholder="简要说明项目情况">${project ? escapeHtml(project.description) : ''}</textarea>
    </label>
    <p class="form-error" id="m-error"></p>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="m-cancel">取消</button>
      <button class="btn btn-primary" id="m-save">${isEdit ? '保存' : '创建'}</button>
    </div>`);

  $('#m-cancel').addEventListener('click', closeModal);
  $('#m-save').addEventListener('click', async () => {
    const name = $('#m-name').value.trim();
    if (!name) { $('#m-error').textContent = '请填写项目名称'; return; }
    const body = { name, location: $('#m-location').value.trim(), description: $('#m-desc').value.trim() };
    try {
      if (isEdit) {
        await api(`/api/projects/${project.id}`, { method: 'PUT', body });
      } else {
        await api('/api/projects', { method: 'POST', body });
      }
      closeModal();
      if (isEdit) { await openProject(project.id); } else { await loadProjects(); }
      toast(isEdit ? '已保存' : '项目已创建');
    } catch (err) {
      $('#m-error').textContent = err.message;
    }
  });
}

/* —— 删除项目确认 —— */
function openDeleteConfirm() {
  openModal(`
    <h3>删除项目</h3>
    <p class="muted">确定删除项目「${escapeHtml(currentProject.name)}」吗？</p>
    <p class="muted">项目下的所有文档与文件将被一并删除，此操作不可恢复。</p>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="d-cancel">取消</button>
      <button class="btn btn-danger" id="d-confirm">确认删除</button>
    </div>`);
  $('#d-cancel').addEventListener('click', closeModal);
  $('#d-confirm').addEventListener('click', async () => {
    try {
      await api(`/api/projects/${currentProject.id}`, { method: 'DELETE' });
      closeModal();
      showView('view-workbench');
      await loadProjects();
      toast('项目已删除');
    } catch (err) {
      toast(err.message, true);
    }
  });
}

/* —— 修改自己的密码 —— */
function openChangePassword() {
  openModal(`
    <h3>修改密码</h3>
    <label class="field"><span>原密码</span><input type="password" id="c-old" /></label>
    <label class="field"><span>新密码（至少 6 位）</span><input type="password" id="c-new" /></label>
    <p class="form-error" id="c-error"></p>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="c-cancel">取消</button>
      <button class="btn btn-primary" id="c-save">保存</button>
    </div>`);
  $('#c-cancel').addEventListener('click', closeModal);
  $('#c-save').addEventListener('click', async () => {
    const oldPassword = $('#c-old').value;
    const newPassword = $('#c-new').value;
    if (newPassword.length < 6) { $('#c-error').textContent = '新密码至少 6 位'; return; }
    try {
      await api('/api/auth/password', { method: 'POST', body: { oldPassword, newPassword } });
      closeModal();
      toast('密码已修改');
    } catch (err) { $('#c-error').textContent = err.message; }
  });
}

/* —— 用户管理（管理员）—— */
async function openUserManagement() {
  openModal(`
    <h3>用户管理</h3>
    <div id="user-list" class="user-list">加载中…</div>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="u-close">关闭</button>
    </div>`);
  $('#u-close').addEventListener('click', closeModal);
  await loadUserList();
}

async function loadUserList() {
  try {
    const data = await api('/api/users');
    renderUserList(data.users || []);
  } catch (err) {
    $('#user-list').innerHTML = `<p class="muted">加载失败：${escapeHtml(err.message)}</p>`;
  }
}

function renderUserList(list) {
  $('#user-list').innerHTML = list.map((u) => `
    <div class="user-row">
      <div class="user-info">
        <div class="u-name">${escapeHtml(u.displayName)} <span class="muted">@${escapeHtml(u.username)}</span>${u.isAdmin ? ' <span class="admin-tag">管理员</span>' : ''}</div>
        <div class="muted u-meta">注册于 ${escapeHtml(u.createdAt || '')}</div>
      </div>
      <div class="u-actions">
        <button class="btn btn-ghost btn-sm" data-act="reset" data-id="${u.id}" data-name="${escapeHtml(u.displayName || u.username)}">重置密码</button>
        ${u.isAdmin ? '' : `<button class="btn btn-ghost btn-sm danger" data-act="del" data-id="${u.id}" data-name="${escapeHtml(u.displayName || u.username)}">删除</button>`}
      </div>
    </div>`).join('');

  $('#user-list').querySelectorAll('[data-act="reset"]').forEach((b) => {
    b.addEventListener('click', () => openResetPassword(b.dataset.id, b.dataset.name));
  });
  $('#user-list').querySelectorAll('[data-act="del"]').forEach((b) => {
    b.addEventListener('click', () => deleteUser(Number(b.dataset.id), b.dataset.name));
  });
}

function openResetPassword(id, name) {
  openModal(`
    <h3>重置密码</h3>
    <p class="muted">为用户「${escapeHtml(name)}」设置新密码</p>
    <label class="field"><span>新密码（至少 6 位）</span><input type="password" id="r-new" /></label>
    <p class="form-error" id="r-error"></p>
    <div class="modal-actions">
      <button class="btn btn-ghost" id="r-cancel">取消</button>
      <button class="btn btn-primary" id="r-save">保存</button>
    </div>`);
  $('#r-cancel').addEventListener('click', closeModal);
  $('#r-save').addEventListener('click', async () => {
    const pwd = $('#r-new').value;
    if (pwd.length < 6) { $('#r-error').textContent = '密码至少 6 位'; return; }
    try {
      await api(`/api/users/${id}/reset-password`, { method: 'POST', body: { password: pwd } });
      closeModal();
      toast('密码已重置');
    } catch (err) { $('#r-error').textContent = err.message; }
  });
}

async function deleteUser(id, name) {
  if (!confirm(`确定删除用户「${name}」吗？\n其名下所有项目与文档将一并删除，且不可恢复。`)) return;
  try {
    await api(`/api/users/${id}`, { method: 'DELETE' });
    toast('用户已删除');
    await loadUserList();
  } catch (err) {
    toast(err.message, true);
  }
}

/* ============ 事件绑定 ============ */
function bindEvents() {
  document.querySelectorAll('.tab').forEach((t) => {
    t.addEventListener('click', () => setAuthMode(t.dataset.mode));
  });
  $('#auth-form').addEventListener('submit', handleAuthSubmit);
  $('#btn-logout').addEventListener('click', async () => {
    await api('/api/auth/logout', { method: 'POST' });
    currentUser = null;
    showView('view-login');
  });
  $('#btn-change-password').addEventListener('click', openChangePassword);
  $('#btn-manage-users').addEventListener('click', openUserManagement);
  $('#btn-new-project').addEventListener('click', () => openProjectModal(null));
  $('#btn-new-project-empty').addEventListener('click', () => openProjectModal(null));
  $('#btn-back').addEventListener('click', () => { showView('view-workbench'); loadProjects(); });
  $('#btn-edit-project').addEventListener('click', () => openProjectModal(currentProject));
  $('#btn-delete-project').addEventListener('click', openDeleteConfirm);
  $('#modal-overlay').addEventListener('click', (e) => {
    if (e.target === $('#modal-overlay')) closeModal();
  });
}

/* ============ 启动 ============ */
async function boot() {
  bindEvents();
  try {
    const data = await api('/api/auth/me');
    currentUser = data.user;
    await enterWorkbench();
  } catch (e) {
    showView('view-login');
  }
}

boot();
