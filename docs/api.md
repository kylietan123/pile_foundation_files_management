# API 清单

所有接口默认使用同源 Cookie 会话。写接口还需要请求头：

```http
X-CSRF-Token: <从 /api/me 或登录响应获取>
```

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/auth/login` | 账号密码登录 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `GET` | `/api/me` | 当前用户、可访问项目和 CSRF Token |

## 项目与阶段

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/projects` | 当前用户可访问的项目 |
| `GET` | `/api/projects/:projectId/dashboard` | 项目总览和七阶段统计 |
| `GET` | `/api/projects/:projectId/phases/:phaseId` | 阶段文档类型、责任单位分组和台账 |
| `GET` | `/api/projects/:projectId/audit` | 项目审计日志 |

## 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/projects/:projectId/documents/:documentId` | 文档详情、版本、审批和关联桩位 |
| `POST` | `/api/projects/:projectId/document-types/:docTypeId/documents` | 创建文档并上传首版 |
| `POST` | `/api/projects/:projectId/documents/:documentId/versions` | 追加文档版本 |
| `GET` | `/api/files/:versionId` | 预览文件，支持 HTTP Range |
| `GET` | `/api/files/:versionId?download=1` | 下载文件 |

## 上传表单字段

| 字段 | 首版上传 | 新版本 | 说明 |
|---|---|---|---|
| `file` | 必填 | 必填 | 实际文件 |
| `title` | 可选 | 不适用 | 默认使用文档类型名称 |
| `doc_no` | 可选 | 不适用 | 留空自动编号 |
| `change_log` | 可选 | 建议填写 | 上传或版本说明 |
| `pile_numbers` | 可选 | 可选 | 逗号、顿号或空格分隔的桩号 |

## 权限错误

| HTTP 状态 | 业务码 | 含义 |
|---|---|---|
| `401` | `UNAUTHORIZED` | 未登录或会话过期 |
| `403` | `INVALID_CSRF` | CSRF Token 无效 |
| `403` | `PROJECT_FORBIDDEN` | 无项目访问权限 |
| `403` | `UPLOAD_FORBIDDEN` | 当前单位无该文档类型上传权限 |
| `413` | `FILE_TOO_LARGE` | 文件超过服务端上限 |
| `400` | `FILE_TYPE_NOT_ALLOWED` | 文件扩展名不在允许范围 |
