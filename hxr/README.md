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
| **oyx** | 单位 × 阶段 × 责任等级权限矩阵；两级签认；文件版本四条铁律；文件台账与“现在在谁手上”；设计参数溯源；设计变更影响分析；问题闭环；知识库；AI 引用治理；584 项测试（合并版全量脚本已通过）；Vue + FastAPI 前后端分层。 | 作为 `new/` 的主架构、数据模型和业务实现；项目详情、阶段导航、业务入口全部沿用 oyx。 |

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
