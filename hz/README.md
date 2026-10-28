# 桩基工程全过程管理文档平台（合并版）

本目录（`hxr/`）就是合并版主干代码，三版原型已经合并进这一份：

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
| **oyx** | 单位 × 阶段 × 责任等级权限矩阵；两级签认；文件版本四条铁律；文件台账与“现在在谁手上”；设计参数溯源；设计变更影响分析；问题闭环；知识库；AI 引用治理；584 项测试（合并版全量脚本已通过）；Vue + FastAPI 前后端分层。 | 作为主干架构、数据模型和业务实现；项目详情、阶段导航、业务入口全部沿用 oyx。 |

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
cd backend

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

如果本机 5173 / 8000 已被别的副本占用，不用改代码，用环境变量换端口即可：

```powershell
# 后端换个端口
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010

# 前端换个端口，并把 /api 代理指到上面的后端
$env:VITE_PORT = "5180"
$env:VITE_API_TARGET = "http://127.0.0.1:8010"
npm run dev -- --port 5180 --strictPort
```

### 3. 测试

```bash
cd backend
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
| `POST` | `/api/v1/projects` | 工作台新建项目，并创建 7 个阶段（仅建设单位可调用） |
| `PATCH` | `/api/v1/projects/{id}` | 修改项目基础信息 |
| `POST` | `/api/v1/projects/{id}/approve` | 建设单位管理员审核通过项目（待审核 → 进行中） |
| `GET` | `/api/v1/projects/{id}/member-candidates` | 可添加的项目参与人员 |
| `POST` | `/api/v1/projects/{id}/members` | 添加项目参与人员并配置可见阶段 / 责任覆盖 |
| `PATCH` | `/api/v1/auth/me` | 个人设置：修改本人电话与邮箱 |
| `POST` | `/api/v1/auth/change-password` | 本人修改登录密码 |
| `GET` | `/api/v1/catalog/documents` | 查询标准文档清单，可用 `stage` 过滤 |
| `GET` | `/api/v1/projects/{id}/pile-selection/options` | 桩基选型：可选桩型（含典型参数）与条件说明 |
| `POST` | `/api/v1/projects/{id}/pile-selection/suggest` | 桩基选型试算（不落库，可反复调条件） |
| `GET` | `/api/v1/projects/{id}/pile-selection` | 读取已保存的选型方案 |
| `PUT` | `/api/v1/projects/{id}/pile-selection` | 保存 / 确认选型方案（需设计阶段编辑权） |
| `POST` | `/api/v1/projects/{id}/pile-selection/report` | 生成《桩基评估》报告（试算，不落库） |
| `PUT` | `/api/v1/projects/{id}/pile-selection/report` | 生成并保存报告（需设计阶段编辑权） |
| `GET` | `/api/v1/projects/{id}/pile-selection/report.txt` | 下载报告 TXT，`?download=1` 强制另存为 |
| `GET` | `/api/v1/admin/overview` | 管理概览（总管理员 / 部门管理员范围不同） |
| `GET` | `/api/v1/admin/options` | 单位、项目、阶段、责任等级选项 |
| `GET` | `/api/v1/admin/users` | 账号列表，可用 `keyword` 过滤 |
| `POST` | `/api/v1/admin/users` | 创建员工账号并分配项目权限 |
| `PATCH` | `/api/v1/admin/users/{id}` | 修改账号资料 / 启用停用 / 设置部门管理员 |
| `POST` | `/api/v1/admin/users/{id}/reset-password` | 重置密码（仅总管理员） |
| `POST` | `/api/v1/admin/users/{id}/permissions` | 给账号分配项目权限 |
| `DELETE` | `/api/v1/admin/users/{id}/permissions/{member_id}` | 吊销单个项目权限 |

原 oyx 接口仍保持路径和响应格式不变。

---

## 七、目录结构

```text
hxr/
├── README.md
├── backend/
│   ├── app/
│   │   ├── api/                   # auth、admin、projects、documents、changes、issues、catalog…
│   │   ├── core/                  # 权限矩阵、认证、数据库、时间类型
│   │   ├── models/                # 34 张业务表
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
│       ├── views/AdminConsoleView.vue  # 系统 / 部门管理员控制台
│       ├── views/ProfileView.vue       # 个人设置
│       ├── views/PileSelectionView.vue # 桩基选型（设计阶段）
│       └── …                           # oyx 原有业务页面
└── docs/                          # 数据库结构、权限设计、截图等
```

---

## 八、当前边界

- 登录页暂不开放自助注册，账号仍由 oyx 的种子数据/统一身份认证提供；如需开放，应由管理员确认单位与项目范围后再加入。
- 工作台支持新建和编辑项目，暂不提供删除项目，避免误删跨表业务数据。
- 新建项目由建设单位发起，先进入“待审核”，经建设单位管理员审核通过后才进入进行中；
  默认从“前期调研”开始，也可以在创建时指定起始阶段（之前的阶段自动标记为已完成）。
- 合并版不包含 hxr 的 Express 服务或 kylie 的纯 Node 服务；它们的数据能力已由 oyx 服务层覆盖。

---

## 九、常见问题

### 下载的文件打不开 / 点下载后新标签页是空白

两件事曾经同时存在，现在都已修：

1. **内容**：演示种子文件原来只是把一句中文文本标成 `application/pdf` 存进 `storage/`
   （七十几个字节），能下载但任何阅读器都打不开。现在 `app/services/demo_files.py`
   用标准库生成**合规的单页 PDF**（`%PDF-1.4` 头、xref 正确、`%%EOF` 收尾），
   能在阅读器里正常打开并核对文件编号 / 版本 / 状态。
   > 正文只有 ASCII —— 中文字形要嵌 CJK 字体，为保证"任何阅读器都能显示"才这么定。
2. **打开方式**：`GET /api/v1/files/{file_id}/download` 原来一律
   `Content-Disposition: attachment`，而前端是 `window.open(url)` ——
   结果新标签页空着、文件悄悄进了下载目录。现在对 PDF / 图片 / 文本返回
   **`inline`**（浏览器直接内嵌预览），需要另存为时加 `?download=1`。
   界面上「查看」= 内嵌预览，「下载」= 强制另存为。

自检命令：

```powershell
cd backend
.venv\Scripts\python.exe scripts\test_download.py    # 会校验下载到的字节是不是合规 PDF
```

### Vite 报错 `connect ECONNREFUSED 127.0.0.1:8000`

这是前端已启动、但 FastAPI 后端没有启动。登录页本身正常，只是 `/api` 代理不到后端。

先在单独终端启动后端：

```bash
cd "<项目根目录>/hxr/backend"
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
cd "<项目根目录>/hxr"
npm run dev
```

可用以下命令检查后端：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

---

## 十、系统管理员与部门管理员控制台

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

> 数据落点：`user_org.is_unit_admin`（部门管理员）与 `project_member.responsibility_override`
> （项目级阶段责任覆盖）。两者都是**追加列**，不改变《管理流程》全局矩阵。

---

## 十一、个人设置

点击页面右上角的姓名或头像，在“退出登录”上方选择“个人设置”，可以：

- 查看姓名、账号、工号、职称、手机、邮箱和所属单位。
- 查看自己在各项目中的参与单位和阶段身份。
- 修改电话和邮箱；姓名、职称、工号由系统管理员维护。
- 使用原密码验证后修改登录密码。

---

## 十二、项目创建与单位审核规则

- 只有建设单位账号可以新建项目，其他参与单位不能调用新建项目接口。
- 建设单位创建项目后，项目状态为“待审核”，此时不能添加其他参与单位。
- 项目创建时会自动把建设单位管理员加入项目；管理员工作台会显示“待我审核”区域。
- 建设单位的单位管理员在项目详情页点击“审核通过”后，项目才进入进行中。
- 审核通过后，系统按《管理流程》矩阵为七个阶段自动设置阶段负责人，并把对应单位管理员加入项目。
- 阶段负责人可以在自己负责的阶段内，为本单位员工分配权限；不能越权管理其他单位或其他阶段。
- 建设单位管理员仍可添加其他单位人员，并配置其可见阶段和阶段责任。
- 只有总管理员可以把员工设置为“部门管理员（领导）”；部门管理员不能设置或停用其他管理员。

### 建设单位施工文件上传演示项目

仓库内提供了一个可重复执行的演示项目创建脚本：

```powershell
cd backend
.venv\Scripts\python.exe scripts\create_owner_construction_demo.py
```

创建结果：

- 项目名称：`建设单位桩基施工文件上传演示项目`
- 登录账号：`chenkaili / Tjad@2026`
- 参与单位：建设单位
- 当前阶段：桩基施工
- 施工阶段权限：上传、提交、发布

该权限通过 `project_member.responsibility_override` 只作用于这个演示项目，不改变《管理流程》全局矩阵。

---

## 十三、桩基选型模块（设计阶段）

把桌面「选型」软件的**完整评估流程**搬进了设计阶段，作为与「文件与版本 / 设计输入管理 / 设计变更 / 问题管理 / 设计成果 / 文件台账」并列的模块。

- 入口：项目 → 设计阶段 → **桩基选型**（`StageContextBar` 里的同名标签）
- 权限：查看要能进本项目；**保存/确认/出报告需要设计阶段的编辑权**（与上传文件同一套判定）
- 落库：`pile_selection` 表（一项目一条），保存时冻结一份引擎建议快照，便于事后解释"当初为什么这么选"

### 流程（与原选型软件对齐）

```
一、建筑概况（面积/层数/覆土/折算厚度）
   ↓
二、项目条件（地铁保护区/内环/高架/密集建筑 → 受限场景；工期/成本/噪声 → 调权重）
   ↓
三、非主楼数据（CAD 实测：投影面积/塔楼投影/柱网；无地下室可留空）
   ↓
四、勘察承载力表（手工录入；有则按直径取承载力、无对应直径走线插法）
   ↓
五、试算选型 → 校对（切桩型自动重填典型参数，桩径/桩长/承载力可改）
   ↓
六、各桩型评分明细（七维加权，排除项说明原因）
   ↓
七、选型理由 + 保存草稿 / 确认方案
   ↓
八、生成《桩基评估》报告 → 预览 / 下载 TXT
```

**报告全文由确定性规则拼接，不经过大模型**，格式与历史交付报告逐字一致
（古美样例作为黄金标准，见 `scripts/test_pile_report.py`，78 行逐字比对）。

> 界面上有「**填入古美样例**」按钮：点它 → 试算 → 保存 → 生成报告，
> 可直接验证"出来的报告和历史报告一模一样"。

### 与原软件的唯一差别

| 项 | 原软件 | 本平台 |
|---|---|---|
| 勘察报告 PDF 自动提取参数 | DeepSeek 解析 + 正则兜底 + 手动表单 | **仅手工录入**（平台不接大模型，见下）|
| 报告标题 | 写死「中海前期地块桩基评估」 | 默认「桩基评估」，可在界面改 |
| 其余 | — | 桩型评分、权重、桩径规则、桩数估算公式、报告格式**全部原样保留** |

**为什么不做 PDF 自动提取**：那一步依赖 DeepSeek API key（解析一次几分钱）＋扫描件 OCR，
属"外部服务依赖"，与本平台"内部试用、数据不出本机"的定位冲突。
需要时可按同一接口形状再挂：`geo.capacity_rows` 就是解析结果要填的结构，
前端把提取结果回填到「四、勘察承载力表」即可，其余流程不用改。

### 做了什么（流程）

1. **建筑概况**：容积率、用地/地上/地下/总建筑面积、单体数、地上层数（"1,11,14"）、高度范围、地下层数/层高、覆土厚度、室内外高差、顶板/中板/底板折算厚度 —— 报告第 1 节直接由它渲染；
2. **项目条件**：地铁 50m 保护区 / 内环内 / 临近高架 / 周边建筑密集（硬性限制，排除挤土桩）+ 噪声敏感 / 工期紧 / 成本敏感 / 环保严格 / 砂层 / 立柱桩 / 内支撑；
2. **试算**：规则引擎按七维加权打分排序（`工程成本/工期/挤土效应/噪声/承载力/技术成熟度/适用性`），给出主楼与纯地下室两个建议；
3. **桩参数**：桩径按院版《桩基方案》第五、六章选型图规则（高度带 / 地下层数，区间取小、地铁保护区取图内直标）；勘察承载力表有对应直径行则直接用行值，没有则用其他直径行**线插法**取值，都没有才回落典型组合；
4. **校对**：桩型可在下拉里改（切换时用后端典型参数组合就地重填），桩径/桩长/承载力可手工微调；
5. **保存 / 确认**：`DRAFT` 草稿或 `CONFIRMED` 已确认，确认人、确认时间与审计日志一并留痕。

### ⚠️ 依据规则（重要）

规则引擎在没有勘察数据时**也能算**——用 `PILE_COMBOS` 里的典型组合（历史项目经验值）。
那是"方案初判"，**不是设计依据**，所以：

- 试算结果带 `basis` 字段：`survey`（至少一侧匹配到勘察承载力表行）/ `typical`（只有典型组合）；
- 界面在 `typical` 时醒目告警，并给桩参数打上"无勘察依据 · 典型组合"标记；
- **`CONFIRMED` 必须有勘察依据**：服务端重新跑一遍参数匹配，两侧都没匹配到勘察表行时
  返回 400（"确认选型需要勘察依据…"）。没有依据时仍可保存 `DRAFT` 草稿。

要拿到有依据的结论：把勘察报告里的《单桩竖向承载力估算表》抄进「四、勘察承载力表」
（桩型描述 + 桩径 + 桩长 + 持力层 + Ra/Rd/Rtd），再点试算。

### 代码位置

| 层 | 文件 | 说明 |
|---|---|---|
| 知识库 | `backend/app/services/pile_selection_rules.py` | 桩型评分、权重、典型参数组合、桩径规则、估算常量、报告措辞 |
| 选型引擎 | `backend/app/services/pile_selection.py` | 排除/加权/排序、高度带、桩径规则、线插法、参数匹配、选型理由 |
| 数量估算 | `backend/app/services/pile_calc.py` | 主楼承压桩数、地下室抗拔需求、非主楼桩数、每千平米桩数 |
| 报告生成 | `backend/app/services/pile_report.py` | 模板 + 概况节 + 勘察注记 + 全文拼接（逐字对齐历史报告） |
| 模型 | `backend/app/models/pile_selection.py` | `pile_selection` 表（条件/概况/勘察/结论/快照/报告全文） |
| 接口 | `backend/app/api/pile_selection.py` | options / suggest / get / save / report / report.txt |
| 页面 | `frontend/src/views/PileSelectionView.vue` | 概况 → 条件 → 非主楼 → 勘察 → 校对 → 评分 → 报告 |
| 测试 | `backend/scripts/test_pile_selection.py` | 60 项：原软件用例回归 + 接口 + 权限边界 + 依据门槛 |
| 测试 | `backend/scripts/test_pile_report.py` | 33 项：报告全文**逐字**回归（78 行）+ 章节省略 + 生成下载 |

> 说明：**没有搬**的是原软件的三个外围能力 —— ①建筑概况文本/勘察 PDF 的 LLM 解析、
> ②Word 导出（本平台出 TXT，够粘进汇报材料）、③问答/规范库/案例库/矛盾诊断四个辅助模块。
> ①②依赖 DeepSeek API key；③需要本地向量库和 88 份历史报告语料。
> 选型与报告这条主线**不联网、不调模型**，可单测。

原软件改规则后如何同步：
- 知识库/常量 → 同步 `pile_selection_rules.py` 里 `PILE_KNOWLEDGE / WEIGHTS_* / PILE_COMBOS / DIAMETER_RULES / PILE_LABEL_BY_TYPE / REDUND_PCT / LOAD_ABOVEGROUND_T_M2` 等；
- 公式 → `pile_calc.py`；措辞/格式 → `pile_report.py`（改完跑 `test_pile_report.py`，逐字回归会挡住格式偏移）。

---

## 十四、管理员相关脚本

```powershell
cd backend

# 把建设单位管理员补入本单位所有历史项目（幂等）
.venv\Scripts\python.exe scripts\sync_owner_unit_admins.py

# 三个管理员相关的测试套件（已包含在 run_all_tests.py 里）
.venv\Scripts\python.exe scripts\test_admin_console.py   # 总管理员控制台
.venv\Scripts\python.exe scripts\test_unit_admin.py      # 部门管理员范围与边界
.venv\Scripts\python.exe scripts\test_profile.py         # 个人设置

# 桩基选型：规则引擎回归（对齐原「选型」软件用例）+ 接口 + 权限边界
.venv\Scripts\python.exe scripts\test_pile_selection.py
```

