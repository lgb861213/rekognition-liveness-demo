# feat: Token 鉴权 + 会话绑定 + AttemptId 状态机（安全增强）

## 概述
将活体检测从「无鉴权、裸 SessionId」升级为生产级安全流程：Token 鉴权 →
`AccountId↔AttemptId↔SessionId` 绑定 → 结果获取前二次校验 → AttemptId 状态机
（防重放/防越权/防过期）。前端加登录门禁，所有端点需鉴权。

## 基础版 (main) vs 安全增强版 (本 PR) 差异对比

| 维度 | 基础版 (main) | 安全增强版 (本 PR) |
|---|---|---|
| 鉴权 | ❌ 无，任何人可调 | ✅ Token(Bearer) 校验，401 拦截 |
| 会话绑定 | ❌ 裸 SessionId | ✅ AccountId↔AttemptId↔SessionId 持久化 |
| 结果获取 | 直接用 SessionId 查 | 先二次校验绑定关系再查 |
| 防重放 | ❌ | ✅ AttemptId 状态机（终态不可复用） |
| 防越权 | ❌ | ✅ 账号不匹配拒绝 (403) |
| 会话过期 | 依赖 AWS 3min | ✅ 后端 TTL 180s 显式失效 |
| 前端 | 直接调用 | ✅ 登录门禁 + 全程带 Token |
| 端点保护 | 全部公开 | ✅ 除 /health 外全部需鉴权 |
| 适用场景 | 快速验证/演示 | 贴近生产/合规 |

> 流程对比图：`docs/flow-comparison.drawio`

## 主要改动
- `backend/auth.py`：mock Bearer token → AccountId（`verify_token` 为真实 JWT/OIDC 接入点）
- `backend/binding_store.py`：绑定存储 + AttemptId 状态机（CREATED→COMPLETED/FAILED/EXPIRED）+ TTL 180s（内存实现，含 DynamoDB 映射说明）
- `backend/main.py`：新增 `/api/secure/liveness/session` 与 `.../attempt/{id}/complete`；所有业务端点加 `require_account`，仅 `/health` 公开；移除无鉴权旧端点
- `frontend`：登录页（Token 快捷选择）+ 全程 `Authorization: Bearer` + 活体走绑定流程
- `docs`：TESTING.md 安全流程章节、README 更新、流程对比图

## 测试
- 单元测试 `backend/test_binding_auth.py`：**11 passed**（鉴权/绑定/状态机/重放/过期）
- 真实 AWS 集成：无 token→401、有效→200、错误账号/会话/未知 attempt→403，均符合预期
- 未授权所有业务端点→401；前端生产构建 0 错误

## 安全说明
- Demo 用 mock token；生产替换 `verify_token()` 为真实验签
- 生产可将内存绑定存储换为 DynamoDB（含 TTL）
- 生产用 IAM Role 而非长期密钥
