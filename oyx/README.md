# 桩基工程全生命周期管理平台

面向**参与单位协同**的多项目、多单位、多阶段**工程文档管理**平台。

> **定位（会上已定）**：核心是**文档管理** —— 解决工程周期长、文件易丢、
> 参与方多、责任难追的问题。**不做**设计计算与出图（现有软件已成熟）。
> 主体是**参与单位**，不是"设计人/校核人"这类岗位。

7 个阶段：前期调研 → 勘察 → 设计试桩 → **设计** → 施工 → 验收试桩 → 运维监测

---

## 一、当前状态

| 模块 | 状态 | 验证方式 |
|---|---|---|
| 数据模型（29 张表） | ✅ | `scripts/check_db.py` 结构检查通过 |
| 数据库迁移（Alembic） | ✅ | 已加命名约定，SQLite/PostgreSQL 双向可用 |
| 认证（JWT + PBKDF2） | ✅ | 纯标准库实现，无 cryptography 依赖 |
| **权限引擎（单位 × 阶段 × 责任等级）** | ✅ | **权限由《管理流程》矩阵推导**，见下 |
| **两级签认工作流** | ✅ | 主办单位确认 → 相关单位复核（可多个并行） |
| 项目列表接口（按权限过滤） | ✅ | 非参与单位看不到项目 |
| 字典接口（统一 ID） | ✅ | 11 个分类 / 65 个字典项 |
| **文件版本状态机** | ✅ | **四条铁律全部强制校验** |
| **文件台账与追溯** | ✅ | 谁上传、谁签认、**文件现在在谁手上** |
| **我的工作（跨项目交办事项）** | ✅ | 一人多项目场景的刚需 |
| 设计变更与影响分析 | ✅ | 六类影响自动推导，含「已施工部位受影响」高风险判定 |
| 问题管理与闭环 | ✅ | 八段式链路不可跳步，闭环必须先验证 |
| 跨项目知识库 | ✅ | 已闭环问题沉淀为知识条目，AI 检索层的数据来源 |
| 设计成果与交付检查 | ✅ | 六道关卡；未发布版本不可出现在交付清单 |
| AI 检索与问答 | ✅ | 四段式强制、引用必填、权限过滤在检索之前 |
| 前端全部页面 | ✅ | 类型检查零错误，12 个页面端到端截图验证 |

**测试合计 557 项，全部通过（用 `run_all_tests.py` 一键跑）：**
- `scripts/smoke_test.py` —— 45 项（认证、权限、项目、字典）
- `scripts/test_version_rules.py` —— 91 项（状态机四条铁律、两级签认、参数溯源、STALE）
- `scripts/test_change_impact.py` —— 65 项（六类影响识别、关闭互锁、权限边界）
- `scripts/test_issues.py` —— 88 项（链路不可跳步、闭环互锁、知识沉淀前置条件）
- `scripts/test_deliverables.py` —— 56 项（成果清单、交付六道关卡、交付清单）
- `scripts/test_ai.py` —— 62 项（AI 治理规则、检索权限隔离、引用溯源）
- `scripts/test_ledger.py` —— 61 项（台账、责任落点、谁上传谁签认、文件在谁手上）
- `scripts/test_workbench.py` —— 38 项（跨项目待办、被退回、交办事项）
- `scripts/verify_objective.py` —— 45 项（**目标验收**：换主体 / 阶段页 /
  追溯 / 收尾 逐项自动核查，防止改造回退）

> ⚠️ **必须用 `run_all_tests.py` 而不是逐个跑**：
> 各套件会修改共享状态（交付测试锁定设计输入、状态机测试发布版本），
> 直接依次跑会互相污染 —— 单独跑能过、合起来跑就挂。
> 该脚本在每个套件之前重置演示数据。

**尚未开始（等三方会议决策）：**
- 设计计算引擎（卡在"计算档位 A/B/C"决策）
- 桩型选型算法（卡在与郝兮睿选型软件的边界）
- 其他 6 个阶段的业务页面

**接口：60 个路径 / 63 个方法**（见 http://127.0.0.1:8000/docs）

---

## 二、快速开始

### 前置要求

- Python 3.12+
- Node.js 20+
- **不需要** 安装 PostgreSQL（开发期用 SQLite）
- **不需要** 安装 Docker

### 后端

```powershell
cd backend

# 1. 建虚拟环境
python -m venv .venv

# 2. 装依赖 —— ⚠️ 必须带 --use-deprecated=legacy-resolver
#    原因见下方"已知坑"第 1 条
.venv\Scripts\python.exe -m pip install --use-deprecated=legacy-resolver -r requirements.txt

# 3. 建表
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe scripts\check_db.py       # 结构自检

# 4. 写入演示数据
.venv\Scripts\python.exe -m app.seed.seed_all

# 5. 启动
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

后端接口文档：http://127.0.0.1:8000/docs

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173

### 自测

**推荐用一键脚本**（会在每个套件前重置演示数据，避免状态污染）：

```powershell
cd backend
.venv\Scripts\python.exe scripts\run_all_tests.py
```

预期输出：`合计：通过 557 项，失败 0 项`

也可以单独跑某个套件（此时请先自行重置数据）：

```powershell
.venv\Scripts\python.exe -m app.seed.seed_all --reset
.venv\Scripts\python.exe scripts\test_ai.py              # 62 项：AI 治理规则
.venv\Scripts\python.exe scripts\test_deliverables.py    # 61 项：交付六道关卡
```

> ⚠️ `test_version_rules.py` 会在演示项目里创建 `TEST-SM-*` 测试文档。
> 测试结束后设计输入会自动还原为「待核验」，但测试文档会留下。
> **需要干净演示数据时执行：**
> ```powershell
> .venv\Scripts\python.exe -m app.seed.seed_all --reset
> ```

---

## 三、演示账号

密码统一 `Tjad@2026`

| 用户名 | 姓名 | 角色说明 |
|---|---|---|
演示账号覆盖全部 11 个参与单位，密码统一 `Tjad@2026`。

| 用户名 | 姓名 | 参与单位（杭州项目） |
|---|---|---|
| `chenkaili` | 陈铠俐 | **建设单位**（前期调研主办） |
| `ligong` | 李工 | **勘察单位**（勘察主办） |
| `zhaosi` | 赵四 | **设计试桩单位**（设计试桩主办） |
| `ouyuxin` | 欧雨欣 | **设计单位**（设计主办）· 苏州项目是勘察单位 |
| `sunqi` | 孙七 | **总包单位**（施工主办） |
| `zhouba` | 周八 | 分包单位（施工/验收试桩相关） |
| `wangwu` | 王五 | 监理单位（施工/设计相关） |
| `wujiu` | 吴九 | **验收试桩单位**（验收试桩主办） |
| `zhengshi` | 郑十 | **检测监测单位**（运维监测主办） |
| `gongwu` | 龚武 | 政府审查单位（只读 + 提意见） |
| `haoxirui` | 郝兮睿 | 兼勘察单位与设计试桩单位（**一人在同一项目两个身份**） |
| `admin` | 系统管理员 | 平台角色（唯一超管） |

**建议用 `ouyuxin` 和 `wangwu` 各登录一次对比**，能直观看到权限差异：
设计单位在「设计」阶段能上传发布，监理单位只能查看与签意见。

> ⚠️ 登录页的演示账号列表在正式部署前必须移除。
> ⚠️ **除 admin 外都不设超管** —— 超管会绕过全部校验，
> 那样就完全看不出"单位 × 阶段 × 责任等级"的差异了。

> ⚠️ 登录页的演示账号列表在正式部署前必须移除。

---

## 四、目录结构

```
app/
├── backend/
│   ├── alembic.ini                  迁移配置（保持 ASCII，见已知坑 2）
│   ├── migrations/                  迁移脚本
│   ├── requirements.txt             依赖（范围约束）
│   ├── requirements.lock.txt        依赖（精确版本）
│   ├── scripts/
│   │   ├── check_db.py              数据库结构自检
│   │   ├── check_demo_data.py       演示数据健康检查
│   │   │                            数量 / 测试残留 / 铁律违反 /
│   │   │                            变更与桩位一致性 / 状态与流程一致性
│   │   ├── run_all_tests.py         ★ 一键跑全部测试（每个套件前重置数据）
│   │   ├── smoke_test.py            认证/权限/项目/字典冒烟测试（45 项）
│   │   ├── test_version_rules.py    版本状态机与参数溯源专项测试（91 项）
│   │   ├── test_change_impact.py    变更影响分析专项测试（65 项）
│   │   ├── test_issues.py           问题链路与知识沉淀专项测试（88 项）
│   │   ├── test_ledger.py           文档台账与追溯专项测试（61 项）
│   │   ├── test_workbench.py        工作台与跨项目待办专项测试（38 项）
│   │   └── verify_objective.py      ★ 目标验收：改造是否回退的自动核查（45 项）
│   │   ├── test_deliverables.py     成果与交付关卡专项测试（61 项）
│   │   └── test_ai.py               AI 治理规则与权限隔离专项测试（62 项）
│   ├── app/
│   │   ├── main.py                  FastAPI 入口 + 统一异常处理
│   │   ├── config.py                全局配置（换数据库/换 LLM 只改这里）
│   │   ├── schemas.py               ★ 接口契约，须与前端 types.ts 同步
│   │   ├── core/
│   │   │   ├── database.py          引擎与会话
│   │   │   ├── security.py          密码哈希 + JWT（纯标准库实现）
│   │   │   ├── permissions.py       ★ 权限引擎（三层校验、多角色并集）
│   │   │   └── types.py             可移植 JSON 类型
│   │   ├── models/                  ★ 29 张表的数据模型
│   │   │   └── base.py              含约束命名约定（见已知坑 6）
│   │   ├── services/                ★ 业务规则的唯一实现（API 层不重复写）
│   │   │   ├── storage.py           内容寻址去重 + 签名下载
│   │   │   ├── documents.py         ★ 版本状态机四条铁律
│   │   │   ├── workflow.py          ★ 两级签认（主办确认 → 相关复核）
│   │   │   ├── design_input.py      参数核验、锁定、STALE 自动推导
│   │   │   ├── change.py            ★ 变更六类影响分析
│   │   │   ├── issue.py             ★ 八段式问题链路 + 知识沉淀
│   │   │   ├── deliverable.py       ★ 交付六道关卡
│   │   │   ├── llm.py               ★ LLM 提供方抽象（none/cloud/local）
│   │   │   ├── retrieval.py         ★ 检索（权限过滤在 SQL 层，只检索已发布）
│   │   │   └── ai.py                ★ 四段式回答 + 引用必填
│   │   ├── api/
│   │   │   ├── deps.py              依赖注入 + 权限断言
│   │   │   ├── auth.py              登录 / 刷新 / me / 阶段选项
│   │   │   ├── projects.py          项目列表（按权限过滤）/ 详情 / 参与人
│   │   │   ├── dicts.py             字典（统一 ID 的对外入口）
│   │   │   ├── documents.py         文档/版本/上传/提交/审批/发布/修订/作废/下载
│   │   │   ├── changes.py           变更/影响分析/处理/通知/审批/关闭
│   │   │   ├── issues.py            问题/处理链路/沉淀知识/知识库检索
│   │   │   ├── deliverables.py      成果清单/交付检查/交付清单
│   │   │   ├── ai.py                提问/会话/反馈/索引/仅检索
│   │   │   ├── design_inputs.py     设计输入清单/核验/锁定/解锁/来源改指/STALE
│   │   │   └── tasks.py             待办（可跨项目）与审批轨迹
│   │   └── seed/                    演示种子数据
│   └── storage/                     上传文件的对象存储目录（gitignore）
├── frontend/
│   ├── vite.config.ts               含代理与 watcher 忽略规则（见已知坑 3）
│   └── src/
│       ├── api/
│       │   ├── types.ts             ★ 接口契约类型，须与后端 schemas.py 同步
│       │   ├── http.ts              拦截器：token 注入 / 401 自动刷新 / postFull 透传 message
│       │   └── index.ts             接口方法
│       ├── stores/                  Pinia：auth（权限）/ project
│       ├── router/                  路由 + 登录守卫
│       ├── layouts/MainLayout.vue   顶栏布局（7 阶段**不**在这一层）
│       ├── components/StageRail.vue 7 阶段迷你进度条
│       └── views/
│           ├── LoginView.vue
│           ├── ProjectListView.vue  ★ 首页 = 我的项目
│           ├── ProjectDetailView.vue ★ 7 阶段导航 + 工作入口
│           ├── DesignInputView.vue  ★ 参数溯源链界面
│           ├── DocumentsView.vue    ★ 版本状态机 + 审批轨迹
│           ├── ChangesView.vue      ★ 变更影响分析 + 受影响桩位清单
│           ├── IssuesView.vue       ★ 八段式问题链路 + 处理时间线
│           ├── KnowledgeView.vue    ★ 跨项目知识库
│           ├── DeliverablesView.vue ★ 交付六道关卡 + 交付清单
│           └── AIChatView.vue       ★ 四段式回答 + 引用溯源 + 仅检索
├── docs/screenshots/                端到端验证截图
└── scripts/                         CDP 工具与端到端截图脚本
```

---

## 五、关键设计决策（三方必须知道）

### 1. 首页是项目列表，7 个阶段是"项目内导航"

**因为一个人会同时参与多个项目。** 如果按阶段做平台级入口，进「设计」时还得再选一次项目，
而且"待我处理 5"是哪个项目的数字说不清。

层级是：**项目 → 阶段 → 业务功能**。

所以：
- `MainLayout.vue`（顶栏）**没有**阶段导航
- `ProjectDetailView.vue`（项目内）**才有** 7 阶段导航
- 每个阶段的内部页面由各负责人独立开发，边界清晰

### 2. 权限主体是「参与单位 × 阶段 × 责任等级」

**权限不是单独配的，是从《管理流程》矩阵推导出来的：**

```
RESPONSIBILITY_MATRIX[阶段][单位] = 责任等级
                ↓  推导
主 办（**）→ 查看 下载 编辑 提交 发布 签认
相 关（*） → 查看 下载 签认 提意见
参 与（√） → 查看 下载
审 查     → 查看 下载 提意见
```

好处：
1. 责任划分调整只改矩阵一处（`models/enums.py`），权限自动跟着变 ——
   不会出现"矩阵说监理负责、代码却拦住监理"这种自相矛盾；
2. 不用为 11 个单位 × 7 个阶段配 77 条权限；
3. 汇报时可以直接把矩阵打出来对照。

阶段范围也**从矩阵推导**，不单独配：矩阵里写了哪些阶段，就自动有哪些阶段的权限。
（`project_member.stage_scope` 仅作项目级覆盖，默认留空表示"按矩阵来"。）

**单位内不区分岗位**：单位里任何人都能上传，
责任通过"每一次操作都记录操作人姓名与工号"来落实，而不是靠限制权限。

三层同时校验：
1. **单位** — 你是不是本项目的参与单位（`scoped_project_query`，**过滤发生在 SQL 层**）
2. **阶段** — 这个阶段你有没有责任
3. **动作** — 你的责任等级允许做这个动作吗

> 前端隐藏按钮只是体验，**不是安全措施**。后端每个接口独立校验。

**矩阵上有一格是经确认后补的（重要，别当成多余权限清掉）：**

《管理流程》原矩阵在「勘察阶段 × 设计单位」这一格**没有打 √**。
但设计必须参照勘察资料 —— 不补这一格，设计人员在系统里**看不到勘察报告**，
设计输入文件库就是空的。**2026-10-13 经确认补入，定为 `PARTICIPANT`（只读）**：

| 检查点 | 结论 |
|---|---|
| 设计单位能否查阅勘察报告 | ✅ 能（否则没法设计） |
| 设计单位是否承担勘察阶段责任 | ❌ 不承担，勘察阶段主办单位仍是**勘察单位** |
| 设计单位能否上传/编辑勘察文件 | ❌ 不能 |
| 设计单位能否签认勘察文件 | ❌ 不能（`PARTICIPANT` 只有查看与下载） |

这正是 `√`（参与）与 `√*`（相关）的区别：**参与 ≠ 责任**。
代码位置：`app/models/enums.py` 的 `RESPONSIBILITY_MATRIX[INVESTIGATION]`。
`scripts/test_ledger.py` 第 10 组与 `scripts/verify_objective.py` 都有断言守着这条。

### 3. 统一 ID 原则

"钻孔灌注桩 φ1200"在勘察、设计、施工、验收四个阶段**必须是同一个字典项、同一个 ID**。
各阶段不得自建桩型 / 土层 / 单位列表，一律从 `/dict/items` 取。

这条不做，跨阶段数据互通就是空话。

### 4. 版本状态机

```
草稿 → 校核中 → 审核中 → 已批准 → 已发布 → 已作废
修订循环：已发布 --发起修订--> 修订中 --> 校核中 ...
```

四条铁律，**必须在后端强制拦截**：
1. 未发布版本不可被任何下游引用
2. 同一文件不允许同时存在两个审批中的版本
3. `PUBLISHED` 不可回退，要改就发新版本
4. 同一文件同一时刻最多一个 `PUBLISHED`；作废必须填原因，不允许物理删除

### 5. AI 治理规则（已完整实现，部署方式为配置项）

四条规则**不是建议，是机制**，都有测试守着：

| 规则 | 实现位置 | 怎么保证 |
|---|---|---|
| 回答必须带引用 | `services/ai.py` | `has_citation=False` 时前端不展示 |
| 检索先过权限过滤 | `services/retrieval.py` | 过滤在 **SQL 层**完成，不是拿到结果后再筛 |
| 会话严格限当前项目 | `api/ai.py` | 会话表强制绑 `project_id`，跨项目续聊直接 403 |
| 只把 PUBLISHED 入知识库 | `services/retrieval.py` | 非已发布版本索引请求返回 400 |

输出强制四段式：**结论 / 依据 / 不确定性 / 责任声明**，缺段会被标记 `is_complete=False`。

其中「不确定性」是**主动暴露风险**，不是免责话术 ——
比如"该参数来源刚更新、尚未人工复核"必须说出来。

**部署方式可切换**，改 `.env` 即可（`LLM_PROVIDER=none/cloud/local`）：

- `none`（默认）：**不编造答案**，只返回检索到的原文，
  并在界面上明说"AI 未配置"。这比编一段像模像样的话诚实得多。
- `cloud` / `local`：走同一个 OpenAI 兼容提供方，区别只是 `LLM_BASE_URL` 指向哪里。
  院内自建（vLLM / Ollama）与云端 API 都不需要改代码。

> 这就是把"院内如何部署"从代码问题降成配置问题的做法 ——
> 三方会议定完，填三行配置即可启用。

---

## 六、已知坑（三个人都会遇到，务必看完）

### 1. pip 装依赖会"卡死"，其实是在无限回溯

**现象**：`pip install -r requirements.txt` 跑几分钟没输出，CPU 空转，也不报错。

**原因**：requirements 里固定了精确版本，pip 新版解析器（resolvelib）在寻找满足全部约束的
组合时反复回溯。实测 `sqlalchemy` 下载要 49 秒、`cryptography` 要 62 秒，叠加回溯就看起来像死机。

**解决**：

```powershell
.venv\Scripts\python.exe -m pip install --use-deprecated=legacy-resolver -r requirements.txt
```

**这也解释了我们为什么不用 `passlib` / `python-jose` / `cryptography`** ——
密码哈希与 JWT 全部用标准库 `hmac` + `hashlib` 自己实现（见 `core/security.py`），
少三个依赖，另外两位的环境配置成本显著降低。

### 2. `alembic.ini` 必须保持纯 ASCII

**现象**：`alembic` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte...`

**原因**：Alembic 读取 ini 文件用的是**系统 locale 编码**（这台机器是 GBK），
不是 UTF-8。文件里的中文注释会直接让它崩掉。

**解决**：`alembic.ini` 里只写英文注释。**不要**"顺手"把它翻译成中文。

### 3. Windows 上编辑器保存文件会把 Vite dev server 搞崩

**现象**：dev server 突然退出，报 `EBUSY: resource busy or locked, watch '...tmpdir\...'`

**原因**：某些编辑器/自动化工具保存文件时先写临时目录，Vite 的 fs watcher 去监听这些
临时路径失败，直接抛错退出整个进程。

**解决**：已在 `vite.config.ts` 的 `server.watch.ignored` 里忽略这些路径。
如果你换编辑器后还遇到，往那个列表里加规则。

### 4. SQLite 改字段必须走 batch 模式

`migrations/env.py` 里已设 `render_as_batch=True`。SQLite 不支持 `ALTER COLUMN`，
不加这个参数改字段的迁移会直接失败。

### 5. 不要引入 PostgreSQL 专有类型

开发期 SQLite、生产 PostgreSQL。**禁止使用** `JSONB` / `ARRAY` / `CITEXT`，
否则两边行为不一致。需要 JSON 时用 `app/core/types.py` 的 `json_obj()`。

### 6. 数据库约束必须有名字（否则迁移会失败）

**现象**：`alembic upgrade head` 报 `ValueError: Constraint must have a name`。

**原因**：SQLite 不支持 `ALTER TABLE`，改字段只能靠 batch 模式（重建表 + 复制数据）。
重建时要按名字删除旧约束，如果约束是匿名的就删不掉。

**解决**：`app/models/base.py` 里给 `MetaData` 加了 `naming_convention`，
所有约束都有确定名字。**新增模型时不要绕过这个 Base。**

如果哪天又在迁移里看到这个报错，说明有人新建了独立的 `MetaData` 或
手工写了匿名的 `ForeignKey`（写成 `ForeignKey("t.id", name="fk_xxx")` 可显式命名）。

### 7. 权限判断不要用 `principal.membership()`

一个人在同一项目下**可能有多条成员关系**（种子里郝兮睿在杭州项目既是勘察单位又是设计试桩单位）。

- `principal.membership(pid)` 只返回**第一条**，用于展示，**不能用于权限判断**
- 权限判断必须用：`can()` / `units_in()` / `visible_stages()` / `is_primary_of()`

这几方法都按"**任一角色满足即可**"（并集）语义实现。
早期版本误用 `membership()`（只取第一条成员关系）导致过越权缺陷，已改为取并集并有测试覆盖。

### 8. 删迁移文件必须同时删数据库，否则 Alembic 会卡死

**现象**：删掉 `migrations/versions/*.py` 后，任何 alembic 命令都报
`Can't locate revision identified by 'xxx'`，连 `--autogenerate` 都跑不了。

**原因**：数据库里的 `alembic_version` 表还记着已被删除的 revision，形成死锁 ——
既无法升级（找不到目标 revision），也无法生成新迁移。

**正确的重建顺序（缺一不可）**：

```powershell
# 1. 先停掉占用数据库的进程！否则文件删不掉，你会以为删了其实没删
#    （Windows 上文件被占用时 Remove-Item 会静默失败）
Get-Process python | Stop-Process -Force

# 2. 删迁移脚本
Remove-Item migrations\versions\*.py -Force

# 3. 删数据库（注意路径是 app/pile_lcm.db，不是 backend/ 下面）
Remove-Item ..\pile_lcm.db -Force

# 4. 确认真的删掉了 —— 这一步不要省
Test-Path ..\pile_lcm.db   # 必须是 False

# 5. 重新生成并应用
.venv\Scripts\python.exe -m alembic revision --autogenerate -m "initial schema"
.venv\Scripts\python.exe -m alembic upgrade head

# 6. 重新写入种子数据
.venv\Scripts\python.exe -m app.seed.seed_all --reset
```

**记住**：日常改模型**不需要**这套操作，只需 `alembic revision --autogenerate` +
`alembic upgrade head`。上面这套只在需要**重建迁移基线**时用（本项目在加
约束命名约定、修种子数据缺陷时用过两次）。

### 9. 演示数据也要符合平台规则

种子数据是**手写状态**的，容易绕过服务层的规则。
本项目就踩过：`JG-01` 一度同时存在 V1.0 和 V1.1 两个 `PUBLISHED` 版本 ——
违反了平台自己的铁律 4，导致演示时看不到"发布新版本自动作废旧版本"这个卖点。

**改完种子数据后一定要跑**：

```powershell
.venv\Scripts\python.exe scripts\check_demo_data.py
```

它会检查数量是否符合预期、有没有测试残留、有没有违反铁律 2 / 4 的数据。
**跑完测试后也建议跑一次**，因为 `test_version_rules.py` 会创建 `TEST-SM-*` 文档。

### 10. 流程会"卡死"的三种情形（都已修复，但改模板时要留意）

审批流是最容易出隐蔽 bug 的地方 —— **卡死后用户完全不知道原因**。
以下三种情形本项目都实际踩到过：

**① 签认权限用 EDIT 判断 → 相关单位签不了意见**

监理、政府审查这类**相关单位本就不该有编辑文件的权限**
（否则"改完自己批"无从发现），所以他们不该因为缺 EDIT 就签不了字。
签认权限必须**由"任务是否指派给你"决定**，而不是 EDIT 权限。
见 `api/documents.py` 与 `api/changes.py` 的 `decide` 接口。

**② 模板要求的单位项目里没人 → 任务未指派 → 流程卡住**

新模型下模板按**单位**派任务（`{PRIMARY}` / `{RELATED}`）。
某个相关单位在项目里没配人时，流程会卡住而用户不知道为什么。
`missing_units()` 在提交前校验并给出可操作提示
（"项目里缺少流程要求的参与单位，请先到项目参与单位补齐"），
而不是让流程跑到一半卡死。

**③ 并列任务只取一条 → 另一个单位的人被误判成"非处理人"**

相关单位可能有多个（如"设计"阶段是监理 + 政府审查），
是**并列任务、各签各的**。若只取一条去判断，
另一个单位的处理人会被当成非处理人，进而被要求 EDIT 权限而拒绝其签认
—— 而他们根本没有 EDIT 权限，直接卡死。
必须取**本节点全部待办任务**（`pending_tasks_of_node`）再找属于自己的那条。

**④ 把"发布"做成审批节点 → 同一单位连做确认+发布 → 被职责分离规则拒绝**

**发布是独立的人工动作**（`POST /versions/{id}/publish`），
校审模板的节点应该是 `CHECK → REVIEW → APPROVE` 三个。
**改流程模板时务必确认：同一个角色不会负责两个相邻节点。**

排查方法：卡住时先看
`GET /api/v1/tasks/instances/{id}` 返回的 `current_node` 和任务的 `assignee`，
如果 `assignee` 是 `null`，就是角色没配齐。

### 11. 时间比较必须先过 `as_utc()`，否则首页会 500

**现象**：`TypeError: can't compare offset-naive and offset-aware datetimes`

**原因**：SQLite 不保存时区信息，`DateTime(timezone=True)` 的字段读回来是
**naive datetime**；而 `utcnow()` 返回的是 aware。
两者直接比较就崩。

**这个坑特别阴的地方**：只有当数据库里**真的有数据**时才会触发。
种子里没有待办任务时首页一直正常，一旦让变更流程真正建了流程实例，
首页项目列表立刻 500。

**规则**：任何时间比较前都要过 `app/core/types.py` 的 `as_utc()`，
或者直接用 `is_overdue(due_at)`。**不要写 `if due_at < utcnow()`。**

### 12. 种子数据的状态必须由服务层产生

**现象**：变更卡在「待审批」既不能提交也不能关闭；版本卡在「审核中」永远出不来。

**原因**：手写了 `state=PENDING_APPROVAL` / `state=REVIEWING`，
但**没有建立 workflow_instance**。这些状态在系统里是"到达得了但出不去"的 ——
因为系统产生它们时一定会同时建流程实例，而你手写时跳过了那一步。

**规则**：
- 变更：用 `services/change.submit_for_approval()` 推进状态
- 版本：用 `_start_review_flow()` 建流程并派任务（见 `seed_content.py`）
- 只改 `state` 字段而不建流程 = 制造死状态

`check_demo_data.py` 已加入这类一致性校验，改完种子数据务必跑一次。

---

## 七、数据库：开发期 SQLite，生产切 PostgreSQL

**切换只需改一处** —— `backend/app/config.py`：

```python
DATABASE_URL: str = "postgresql+psycopg://user:pass@host:5432/pile_lcm"
```

前提是装上驱动：

```powershell
.venv\Scripts\python.exe -m pip install --use-deprecated=legacy-resolver psycopg[binary] pgvector
```

**注意**：向量检索（pgvector）是第 8 周 AI 阶段才需要。
按 12 周计划，**第 8 周之前必须把 PostgreSQL 装上**并确认院内是否提供部署环境和管理员权限。

---

## 八、协作约定

> **分发方式（已按实际情况调整）**：三人电脑不在一起，也没有内网 GitLab / 共享盘。
> 因此走 **源码包下发 + patch 回收**：欧雨欣用
> `backend/scripts/make_dist.py` 打约 0.4 MB 的源码包发出去，
> 队友本地 git 提交后导出 `.patch` 回传，由欧雨欣 apply + 跑测试后再合并。
> 详见 `docs/改动汇总流程.md`。

1. **接口先行**：后端先出 OpenAPI，前端按文档开发，不互相等待。
2. **契约同步**：改 `backend/app/schemas.py` 必须同步改 `frontend/src/api/types.ts`。
3. **数据库变更只走 Alembic 迁移**，任何人不得手工改表结构。
   生成迁移后必须人工 review，autogenerate 对类型变更判断经常不准。
   **迁移由欧雨欣在合并后统一生成**（各自生成会产生多个 head）。
4. **演示数据三方共用**：`app/seed/` 那一套，不要各自另造 ——
   跨阶段联合演示时数字对不上，一眼就能看出是假数据。
5. **共享文件只追加不改行**：`main.py`、`schemas.py`、`types.ts`、
   `api/index.ts`、`router/index.ts`、`models/__init__.py`。
   这是让 patch 永远打得上的**唯一最重要纪律** ——
   为了"看起来整齐"重排 import，会让整段变成改动，和队友必然冲突。
6. **公共层不各改**：权限引擎、责任矩阵、版本状态机、签认引擎、字典 ——
   需要改时由欧雨欣统一改，这些文件冲突了非常难合。
7. **回传前必须跑测试**：`run_all_tests.py`（564 项）全过 +
   `npm run typecheck` 零错误。测试不过就别发，让队友去猜比你自己修慢十倍。
8. **小步回传**：patch 只有几 KB，一天一传比攒一周好合一百倍。

---

## 九、下一步

**方向已由会议确定**（不再等决策）：

> 核心是**文档管理** —— 解决工程周期长、文件易丢、参与方多、责任难追。
> **不做**设计计算与出图。主体是**参与单位**。

因此原先的 D1（计算档位）、D2（选型软件边界）**已作废** —— 这两块不做。

**仍然待定：**

| 编号 | 事项 | 影响 |
|---|---|---|
| D3 | 能否对接真实项目数据 | 内部试用的可信度 |
| D4 | 是否需满足院内安全审查 / 等保 | 部署架构 |
| D5 | 部署环境（内网 GitLab？PostgreSQL？） | 正式上线；目前用源码包 + patch 代替 |
| D6 | AI 是否一期启用 | 填 `.env` 即可，代码不用改 |

**改造进度（以参与单位为主体）：**

| 目标 | 状态 |
|---|---|
| (1) 换主体：11 单位角色 + 权限矩阵入库 + 两级签认 | ✅ 已交付 |
| (2) 各阶段页面：文件台账 + 交办事项 | ✅ 已交付（台账/追溯/工作台） |
| (3) 追溯页：谁上传 / 谁确认 / 文件在谁手上 | ✅ 已交付 |
| (4) 收尾：输入文件库、清理无用表、更新汇报材料 | ✅ 已交付 |

**改造已全部交付。下一步可做（按优先级）：**

1. 各阶段页面的进一步细化（阶段内的工作台视图）
2. 前端按需引入优化（当前 Element Plus + ECharts 全量引入，包 1.27MB）
3. 演示账号列表移除（正式部署前必做）
4. PostgreSQL 实测（开发期只用过 SQLite）
5. 对接真实项目数据（等 D3 决策）

> 已完成的收尾项（保留记录，便于回溯决策）：
> - ~~清理不再需要的业务表~~ ✅ 成本/进度/监测共 12 张表
>   （0 行、无业务代码引用）已连同模型移除，表数 37 → 29。
>   因尚未正式部署，直接**重写基线迁移**而不是叠加 drop 迁移，
>   新库不会先建再删。恢复办法见 `app/models/__init__.py` 顶部说明。
> - ~~输入文件库入口~~ ✅ 设计输入页默认落在「输入文件库」，
>   按单位责任自动列出上游（前期调研/勘察/设计试桩）文件，已发布的可下载；
>   原「参数溯源」能力完整保留为第二标签页。

**若要启用 AI**，`.env` 加三行即可：

```ini
LLM_PROVIDER=local                 # 院内本地部署；或 cloud
LLM_BASE_URL=http://10.0.0.5:8000/v1
LLM_MODEL=Qwen2.5-14B-Instruct
# LLM_API_KEY=xxx                  # 本地部署通常不需要
```
