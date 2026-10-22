# 桩基工程全过程管理文档平台（合并版）

`new/` 将三版原型合并为一个可继续开发的平台：

- 以 **oyx 版**为业务底座：权限矩阵、文件版本状态机、两级签认、台账追溯、设计变更、问题闭环、知识库、AI 检索和主要阶段业务页全部保留。
- 登录页与工作台采用 **hxr 版**的轻量体验：单卡片登录、演示账号一键填充、项目汇总卡片、项目网格、新建/编辑项目，点进项目后进入 oyx 版阶段空间。
- 从 **kylie 版**补入 7 阶段 / 84 类标准文档清单，并在项目总览显示“当前阶段标准文档清单”。

> 核心定位仍然遵循 oyx README：这是面向参与单位协同的 **多项目、多单位、多阶段工程文档管理平台**，不做设计计算与出图。
>
> 7 个阶段：前期调研 → 勘察 → 设计试桩 → 设计 → 施工 → 验收试桩 → 运维监测。

---

## 一、三版优点与合并取舍

| 版本 | 值得保留的优点 | 在合并版中的处理 |
|---|---|---|
| **hxr** | 登录/注册入口直观；工作台项目卡片清晰；新建、编辑、删除项目完整；七阶段清单集中在 `config/stages.js`；Express + 原生前端零构建、启动成本低。 | 采用其登录页与工作台视觉和交互；项目新建、编辑已接到 FastAPI；不复制 Express 数据层，避免与 oyx 的 29 张表重复。 |
| **kylie** | 7 阶段 / 84 类文档模板完整；施工阶段 5.1–5.4 分责任单位；历史版本只追加不覆盖；SHA-256 文件指纹；审计日志；责任单位上传、其他单位只读。 | 84 类清单并入后端 `/api/v1/catalog/documents`，在项目总览按当前阶段显示；版本追加、SHA-256、审计与权限由 oyx 的成熟服务层继续承担。 |
| **oyx** | 单位 × 阶段 × 责任等级权限矩阵；两级签认；文件版本四条铁律；文件台账与“现在在谁手上”；设计参数溯源；设计变更影响分析；问题闭环；知识库；AI 引用治理；638 项测试（合并版全量脚本已通过）；Vue + FastAPI 前后端分层。 | 作为 `new/` 的主架构、数据模型和业务实现；项目详情、阶段导航、业务入口全部沿用 oyx。 |

### 合并原则

1. **不重复造数据层**：只保留 oyx 的 FastAPI + SQLAlchemy 数据底座。
2. **外层像 hxr，内层像 oyx**：工作台负责“选项目/建项目”，项目内负责“按 7 阶段办业务”。
3. **文档模板可复用**：kylie 的 84 类清单作为标准基线，不替换实际文件与版本模型。
4. **权限只认一套**：所有项目访问仍由 oyx 的《管理流程》矩阵在 API 层过滤。

---

## 二、合并后的页面流

```text
登录（hxr 风格）
  ↓
工作台：项目汇总 + 项目卡片 + 新建/编辑项目
  ↓ 点击项目
项目总览：oyx 版 7 阶段导航 + 权限提示 + 参与单位 + 标准文档清单
  ↓
设计输入 / 文件与版本 / 设计变更 / 问题管理 / 交付检查 / 文件台账 / 我的工作
```

### 工作台

- 显示参与项目、进行中项目、待办、风险提醒。
- 项目卡片显示当前阶段、7 阶段进度、我以哪个单位参与以及我的责任等级。
- 支持按项目名称、编号、城市搜索。
- 支持新建项目和修改项目基础信息。
- 新建项目会自动创建 7 个 `ProjectStage`，创建人自动成为项目成员。

### 项目阶段

- 项目总览沿用 oyx 的 7 阶段导航。
- 无权限阶段显示为不可进入，并在页面底部解释原因。
- 当前阶段展示 kylie 版标准文档清单，按责任单位分组。
- 原有 oyx 业务页路由全部保留。

---

## 三、技术栈

| 层级 | 技术 |
|---|---|
| 后端 | Python 3.12+、FastAPI、SQLAlchemy 2、Alembic、Pydantic 2 |
| 数据库 | SQLite（开发）/ PostgreSQL（可切换） |
| 认证 | JWT + PBKDF2（标准库实现） |
| 前端 | Vue 3、TypeScript、Vite、Element Plus、Pinia、Vue Router |
| 文件存储 | 本地 `backend/storage/`，可替换对象存储 |
| 测试 | pytest + httpx + 项目自带脚本 |

---

## 四、快速启动

### 1. 后端

```bash
cd new/backend

python3 -m venv .venv
source .venv/bin/activate
pip install --use-deprecated=legacy-resolver -r requirements.txt

alembic upgrade head
python scripts/check_db.py
python -m app.seed.seed_all
python -m uvicorn app.main:app --reload --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>

Windows PowerShell 对应命令：

```powershell
cd new\backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install --use-deprecated=legacy-resolver -r requirements.txt
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m app.seed.seed_all
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd new
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>。Vite 会把 `/api` 代理到 `127.0.0.1:8000`。

### 3. 测试

```bash
cd new/backend
source .venv/bin/activate
python scripts/run_all_tests.py

cd ..
npm run typecheck
npm run build
```

---

## 五、演示账号

统一密码：`Tjad@2026`

| 账号 | 姓名 | 参与单位 / 用途 |
|---|---|---|
| `ouyuxin` | 欧雨欣 | 设计单位 |
| `chenkaili` | 陈铠俐 | 建设单位 |
| `haoxirui` | 郝兮睿 | 勘察 / 设计试桩 |
| `sunqi` | 孙七 | 总包单位 |
| `wangwu` | 王五 | 监理单位 |
| `admin` | 系统管理员 | 跨项目查看与维护 |

---

## 六、合并版新增接口

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/projects` | 工作台新建项目，并创建 7 个阶段 |
| `PATCH` | `/api/v1/projects/{id}` | 修改项目基础信息 |
| `GET` | `/api/v1/catalog/documents` | 查询标准文档清单，可用 `stage` 过滤 |

原 oyx 接口仍保持路径和响应格式不变。

---

## 七、目录结构

```text
new/
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/                   # auth、projects、documents、changes、issues、catalog…
│   │   ├── core/                  # 权限矩阵、认证、数据库、时间类型
│   │   ├── models/                # 29 张业务表
│   │   ├── seed/                  # 演示数据
│   │   ├── services/              # 版本、工作流、变更、问题、交付、AI
│   │   └── data/
│   │       └── document_catalog.json   # kylie 版 7 阶段 84 类清单
│   ├── migrations/
│   └── scripts/                   # 原有测试与数据库检查
├── frontend/
│   └── src/
│       ├── views/LoginView.vue         # 合并版登录（hxr 风格）
│       ├── views/ProjectListView.vue   # 合并版工作台（hxr 风格 + oyx 数据）
│       ├── views/ProjectDetailView.vue # oyx 项目阶段总览
│       └── …                           # oyx 原有业务页面
└── docs/                          # 数据库结构、权限设计、截图等
```

---

## 八、当前边界

- 登录页暂不开放自助注册，账号仍由 oyx 的种子数据/统一身份认证提供；如需开放，应由管理员确认单位与项目范围后再加入。
- 工作台支持新建和编辑项目，暂不提供删除项目，避免误删跨表业务数据。
- 新建项目默认从“前期调研”开始，施工、验收等阶段可按项目实际推进在后续接口中调整。
- 合并版不包含 hxr 的 Express 服务或 kylie 的纯 Node 服务；它们的数据能力已由 oyx 服务层覆盖。

---

## 九、常见问题

### Vite 报错 `connect ECONNREFUSED 127.0.0.1:8000`

这是前端已启动、但 FastAPI 后端没有启动。登录页本身正常，只是 `/api` 代理不到后端。

先在单独终端启动后端：

```bash
cd "/Users/kylie/Desktop/桩基工程全过程管理/new/backend"
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

看到下面的输出后再回到前端操作：

```text
Uvicorn running on http://127.0.0.1:8000
Application startup complete.
```

另一个终端启动前端：

```bash
cd "/Users/kylie/Desktop/桩基工程全过程管理/new"
npm run dev
```

可用以下命令检查后端：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## 十、建设单位施工文件上传演示项目

仓库内提供了一个可重复执行的演示项目创建脚本：

```bash
cd new/backend
source .venv/bin/activate
python scripts/create_owner_construction_demo.py
```

创建结果：

- 项目名称：`建设单位桩基施工文件上传演示项目`
- 登录账号：`chenkaili / Tjad@2026`
- 参与单位：建设单位
- 当前阶段：桩基施工
- 施工阶段权限：上传、提交、发布

该权限通过 `project_member.responsibility_override` 只作用于这个演示项目，不改变《管理流程》全局矩阵。

---

## 十一、系统管理员与部门管理员控制台

总管理员账号：`admin / Tjad@2026`

部门管理员使用各自单位的管理员账号登录，例如设计单位管理员 `ouyuxin / Tjad@2026`。
页面入口在顶部导航：总管理员显示“管理控制台”，部门管理员显示“部门权限”。

### 总管理员

- 创建任意单位的员工账号并设置初始密码、姓名、工号、所属单位。
- 选择参与项目、参与单位、可见阶段和阶段责任覆盖。
- 为已有账号继续分配或取消项目权限。
- 修改员工姓名、职称、工号、电话和邮箱。
- 重置员工密码、启用或停用账号。
- 设置其他账号为“部门管理员（领导）”。
- 查看全部单位、项目和账号。

### 部门管理员

- 只能看到并管理本部门账号，不能看到总管理员或其他部门员工。
- 可以在本部门创建新员工账号，并设置初始密码。
- 只能把本部门员工加入本部门已经参与的项目。
- 只能分配《管理流程》矩阵中本部门有责任的阶段，不能覆盖阶段责任等级。
- 可以为员工取消单个项目权限。
- 停用离职员工账号时，账号状态从启用改为停用（数据库 `is_active` 1 → 0），
  同时吊销其全部有效项目成员关系；账号、历史操作和留痕记录都保留，不做物理删除。
  重新启用账号不会自动恢复旧权限，需要重新分配。
- **不能重置密码**。重置他人密码只有总管理员可以操作；员工本人仍可在“个人设置”中修改自己的登录密码。

普通员工即使手工输入 `/admin` 路由，也无法进入权限管理页面，后端会返回 403。
部门管理员即使手工构造请求，也只能操作本部门范围内的账号与项目。

---

## 十二、个人设置

点击页面右上角的姓名或头像，在“退出登录”上方选择“个人设置”，可以：

- 查看姓名、账号、工号、职称、手机、邮箱和所属单位。
- 查看自己在各项目中的参与单位和阶段身份。
- 修改电话和邮箱；姓名、职称、工号由系统管理员维护。
- 使用原密码验证后修改登录密码。

---

## 十三、项目创建与单位审核规则

- 只有建设单位账号可以新建项目，其他参与单位不能调用新建项目接口。
- 建设单位创建项目后，项目状态为“待审核”，此时不能添加其他参与单位。
- 项目创建时会自动把建设单位管理员加入项目；管理员工作台会显示“待我审核”区域。
- 建设单位的单位管理员在项目详情页点击“审核通过”后，项目才进入进行中。
- 审核通过后，系统按《管理流程》矩阵为七个阶段自动设置阶段负责人，并把对应单位管理员加入项目。
- 阶段负责人可以在自己负责的阶段内，为本单位员工分配权限；不能越权管理其他单位或其他阶段。
- 建设单位管理员仍可添加其他单位人员，并配置其可见阶段和阶段责任。
- 只有总管理员可以把员工设置为“部门管理员（领导）”；部门管理员不能设置或停用其他管理员。
