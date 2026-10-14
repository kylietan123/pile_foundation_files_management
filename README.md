# 桩基工程全过程管理平台

面向桩基工程全生命周期的文档管理与权限控制平台。当前版本重点实现 **桩基施工阶段 5.1–5.4**，同时预置前期调研、地质勘察、设计试桩、工程设计、验收试桩和运维监测七个阶段。

平台采用“文档流驱动业务流”的设计：每类文档绑定责任单位，责任单位可以上传和追加版本，其他参建单位可以查看、预览和下载，但不能修改。权限同时在前端界面与后端 API 中校验。

![桩基施工阶段](docs/platform-preview.png)

## 项目状态

- 版本：`v0.1.0` 原型
- 当前重点：施工阶段 5.1–5.4
- 文档模板：7 个阶段、84 类文档、施工阶段 32 类
- 演示项目：上海市综合体桩基工程
- 运行方式：Node.js 单体服务
- 外部依赖：无

## 核心功能

### 项目管理

- 项目总览和七个阶段进度。
- 必传文档覆盖率、已归档数量、待审核数量和质量预警数量。
- 按阶段查看文档类型、责任单位和文档台账。
- 最近上传记录及操作审计。

### 文档管理

- 责任单位上传文档。
- 支持报告、图纸、模型、照片、视频和压缩包。
- 单个文件默认最大 `200 MB`。
- 文档首版上传后，后续更新只能追加新版本。
- 历史版本永久保留，可在线预览或下载。
- 保存每个文件的 SHA-256 指纹。
- 文档可以关联 `ZH-001` 等具体桩位。
- 需审核文档上传后自动进入“待审核”状态。

### 权限控制

- 每类文档绑定唯一责任单位。
- 只有责任单位中的项目经理、单位管理员或资料员可以上传。
- 其他参建单位只能查看、预览和下载。
- 建设单位演示账号全程只读。
- 系统管理员可以跨单位维护文档。
- 后端重新校验权限，无法通过手工构造请求越权上传。
- 管理员操作同样记录审计日志。

## 技术栈

| 层级 | 技术 |
|---|---|
| 运行时 | Node.js 24 |
| HTTP 服务 | Node.js 原生 `http` |
| 数据库 | Node.js 原生 `node:sqlite` |
| 前端 | HTML、CSS、原生 JavaScript |
| 文件存储 | 本地 `data/uploads/` |
| 测试 | `node:test` |

当前使用零外部依赖方案，便于快速验证业务模型、权限边界和数据库结构。正式部署时可以保留现有接口设计，并将服务层迁移到 NestJS、Spring Boot 或 FastAPI。

## 快速启动

环境要求：

- Node.js `24.x` 推荐；最低使用 `22.13`，以便原生 `node:sqlite` 无需实验标志
- 无需执行 `npm install`，项目没有第三方依赖

启动服务：

```bash
cd /Users/kylie/Desktop/桩基工程全过程管理
npm start
```

浏览器访问：

[http://127.0.0.1:3000](http://127.0.0.1:3000)

开发模式：

```bash
npm run dev
```

查看数据库摘要：

```bash
npm run db:info
```

运行自动化测试：

```bash
npm test
```

## 演示账号

统一密码：

```text
Demo@123456
```

| 账号 | 所属单位 | 权限 |
|---|---|---|
| `contractor` | 工程总包单位 | 上传 5.1，其余只读 |
| `pile_subcontractor` | 桩基分包单位 | 上传 5.2，其余只读 |
| `supervisor` | 工程监理单位 | 上传 5.3，其余只读 |
| `testing` | 检测监测单位 | 上传 5.4，其余只读 |
| `owner_viewer` | 工程建设单位 | 全程只读 |
| `admin` | 系统管理 | 可跨单位维护 |

演示密码只用于本地原型。正式部署前必须修改账号密码，并接入统一身份认证。

## 环境变量

服务直接读取进程环境变量。可用配置如下：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `HOST` | `127.0.0.1` | 监听地址 |
| `PORT` | `3000` | HTTP 端口 |
| `DB_PATH` | `./data/pile-platform.db` | SQLite 数据库路径 |
| `UPLOAD_DIR` | `./data/uploads` | 上传文件目录 |
| `SESSION_HOURS` | `8` | 登录会话有效小时数 |
| `MAX_UPLOAD_MB` | `200` | 单文件大小上限，单位 MB |
| `NODE_ENV` | 未设置 | 设置为 `production` 时启用 Secure Cookie |

示例：

```bash
HOST=0.0.0.0 PORT=8080 npm start
```

## 数据库设计

数据库依据汇报 PPT 中的 ER 图实现。

```text
PROJECT
  └── PROJECT_PHASE
        └── DOC_TYPE
              └── DOCUMENT
                    ├── DOC_VERSION
                    ├── APPROVAL_FLOW
                    ├── QUALITY_ALERT
                    └── DOCUMENT_PILE ── PILE

USER ── USER_PROJECT_ROLE ── PROJECT / UNIT
```

核心数据表：

| 表 | 说明 |
|---|---|
| `projects` | 工程项目 |
| `project_phases` | 项目七阶段实例 |
| `doc_types` | 阶段要求的文档类型 |
| `documents` | 文档实例 |
| `document_versions` | 不可覆盖的文档版本 |
| `approval_flows` | 审批流记录 |
| `quality_alerts` | 质量预警 |
| `units` | 参建单位 |
| `users` | 用户 |
| `user_project_roles` | 用户、项目和单位角色关系 |
| `piles` | 桩位台账 |
| `document_piles` | 文档与桩位多对多关系 |
| `audit_logs` | 操作审计日志 |
| `sessions` | 登录会话 |

详细说明见 [数据库设计文档](docs/database.md)。

## 文档生命周期

1. 项目创建七个 `project_phases`。
2. 每个阶段创建对应的 `doc_types`，并绑定责任单位。
3. 责任单位上传后创建 `documents` 和第一条 `document_versions`。
4. 后续更新只追加 `document_versions`，不覆盖原文件。
5. 需要审核时创建对应的 `approval_flows` 记录。
6. 文档可以关联一个或多个 `piles`。
7. 所有上传操作追加 `audit_logs`。
8. 缺项、超期和异常数据后续可以触发 `quality_alerts`。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/auth/login` | 登录 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/me` | 当前用户和项目权限 |
| `GET` | `/api/projects/:projectId/dashboard` | 项目总览 |
| `GET` | `/api/projects/:projectId/phases/:phaseId` | 阶段文档台账 |
| `POST` | `/api/projects/:projectId/document-types/:docTypeId/documents` | 上传文档首版 |
| `POST` | `/api/projects/:projectId/documents/:documentId/versions` | 上传文档新版本 |
| `GET` | `/api/files/:versionId` | 预览文件 |
| `GET` | `/api/files/:versionId?download=1` | 下载文件 |

完整接口说明见 [API 文档](docs/api.md)，权限规则见 [权限矩阵](docs/permissions.md)。

## 项目目录

```text
桩基工程全过程管理/
├── README.md
├── package.json
├── .env.example
├── public/                     # 前端页面
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── src/
│   ├── server.js               # HTTP 服务和路由
│   ├── data-service.js         # 项目、文档和版本业务
│   ├── permissions.js          # 权限规则
│   ├── auth.js                 # 登录会话
│   ├── security.js             # 密码和 Token
│   ├── http.js                 # HTTP 工具
│   ├── config.js               # 服务配置
│   ├── data/catalog.json       # 84 类文档模板
│   └── db/
│       ├── schema.sql          # 数据库结构
│       └── database.js         # 初始化和种子数据
├── scripts/
│   └── db-info.js
├── test/
│   └── core.test.js
├── docs/
│   ├── database.md
│   ├── permissions.md
│   └── api.md
└── data/
    ├── pile-platform.db
    └── uploads/
```

## 数据重置

如需清空上传记录并重新初始化演示项目，停止服务后删除数据库和上传文件，再次执行 `npm start`：

```bash
rm -f data/pile-platform.db data/pile-platform.db-shm data/pile-platform.db-wal
rm -rf data/uploads/*
npm start
```

该操作会永久删除本地原型数据，请勿在正式环境中使用。

## 测试情况

当前自动化测试覆盖：

- 数据库七阶段和 84 类文档初始化。
- 施工阶段 32 类文档及责任单位绑定。
- 总包、分包、监理、检测和管理员的上传权限。
- 建设单位只读权限。
- 施工阶段四个责任单位分组。
- 项目总览阶段统计。

执行：

```bash
npm test
```

## 正式部署建议

1. 将 SQLite 替换为 PostgreSQL。
2. 将本地磁盘替换为 OSS、S3 或 MinIO 对象存储。
3. 接入企业微信、统一身份认证或短信登录。
4. 启用 HTTPS、Secure Cookie、CSRF 防护和文件病毒扫描。
5. 增加审批人分配、会签、驳回、签章和电子签名。
6. 增加文档缺项、超期、版本异常和检测指标异常的自动预警。
7. 为数据库、对象存储和审计记录配置备份及保留策略。
8. 按项目、阶段、单位和文档类型进一步细分权限。
