# 测试验证指南（Testing Guide）

本文档提供 Demo 的功能验证方法，含 UI 操作、`curl` 接口测试、预期结果与已验证的测试用例。

前置：已按 [DEPLOYMENT.md](./DEPLOYMENT.md) 部署基础设施，后端跑在 `:8000`，前端跑在 `:3000`。

---

## 1. API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/api/liveness/session` | 创建活体会话，返回 `sessionId`（3 分钟有效） |
| GET | `/api/liveness/session/{id}/result` | 原始活体结果 |
| POST | `/api/liveness/session/{id}/verify-enroll` | 活体校验 + 1:N 查重 + 唯一则入库 |
| POST | `/api/collection/enroll` | 图片入库（**先查重，唯一才入库**） |
| POST | `/api/collection/search` | 图片 1:N 查重 |
| GET | `/api/collection/stats` | collection 用户/人脸计数 |
| GET | `/api/collection/users` | 列出所有用户及关联 faceId |
| DELETE | `/api/collection/users/{id}` | 删除用户及其人脸向量 |

---

## 2. 冒烟测试（Smoke Test）

```bash
# 后端存活
curl -s http://localhost:8000/health
# 期望: {"status":"ok","region":"us-east-1","collection":"liveness-demo-collection"}

# 前端存活
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
# 期望: 200

# 计数
curl -s http://localhost:8000/api/collection/stats
# 期望: {"collectionId":"...","faceCount":N,"userCount":N,"exists":true}
```

---

## 3. 活体检测（UI，需摄像头）

1. 浏览器打开 `http://localhost:3000`，点「开始活体检测」。
2. 授权摄像头，完成头部/光照挑战。
3. 完成后后端执行：`GetFaceLivenessSessionResults` → 用参考图 1:N 查重 → 未命中且活体通过则入库。

**预期结果：**
- 活体通过：显示绿色「活体通过」+ 置信度（通常 >90）。
- 首次通过：`🆕 唯一用户，已入库 user-xxxx`。
- 同一人再测：`⚠️ 查重命中已存在用户 user-xxxx（相似度 ~100%）`，不重复入库。

> `isLive` 判定在后端完成（阈值 `LIVENESS_CONFIDENCE_THRESHOLD`），前端返回值不可作鉴权依据（AWS 官方要求）。

---

## 4. Collection 1:N（UI，图片上传，无需摄像头）

右侧「Collection 1:N 测试」面板，支持点击/拖拽上传。

### 4.1 入库（先查重再入库）
- 上传人脸图 A → `🆕 已入库新用户 user-xxxx`。
- 再上传同一人（同图或另一张）→ `⚠️ 已存在用户 user-xxxx，未重复入库`。

### 4.2 1:N 查重
- 上传已入库者的照片 → 命中该 user，显示相似度进度条。
- 上传未入库者的照片 → `未匹配到任何用户`。

### 命令行等价
```bash
# 入库 A（首次 -> 新用户）
curl -s -X POST -F "file=@alice1.jpg" http://localhost:8000/api/collection/enroll
# {"duplicate":false,"userId":"user-xxxx","faceId":"...","matches":[],"message":"...已入库..."}

# 入库 A（再次 -> 重复，不入库）
curl -s -X POST -F "file=@alice2.jpg" http://localhost:8000/api/collection/enroll
# {"duplicate":true,"userId":null,"matches":[{"userId":"user-xxxx","similarity":99.9}],...}

# 查重 B（不同人 -> 无匹配）
curl -s -X POST -F "file=@bob.jpg" http://localhost:8000/api/collection/search
# {"matched":false,"threshold":90.0,"matches":[]}
```

---

## 5. 用户管理（UI + API）

页面底部「已入库用户管理」面板：查看用户表格、单个删除、清空全部、刷新。

```bash
# 列出
curl -s http://localhost:8000/api/collection/users

# 删除单个（同时删除关联人脸向量）
curl -s -X DELETE http://localhost:8000/api/collection/users/user-xxxx
# {"deletedUserId":"user-xxxx","deletedFaceIds":["..."]}
```

---

## 6. 已验证的测试用例（Verified）

以下用例已用真实人脸（活体流程产生的 S3 参考图）实测通过：

| # | 场景 | 输入 | 预期 | 结果 |
|---|---|---|---|---|
| T1 | 活体端到端 | 摄像头真人 | isLive=true, 置信度>90, 入库 | ✅ 置信度 96–98 |
| T2 | 已存在人脸入库 | 库中已有的脸 | `duplicate:true`，计数不变 | ✅ 命中 100% |
| T3 | 空库首次入库 | 清空后上传 | `duplicate:false`，新建 user | ✅ |
| T4 | 首次入库后**立即**重传 | 同图连续两次 | 第 2 次 `duplicate:true`，最终 1/1 | ✅ 走 face 向量查询 |
| T5 | 删除用户 | DELETE user | user+face 均删除，计数下降 | ✅ 3/3 → 2/2 |
| T6 | 非人脸图入库 | 无脸图片 | 报错（无有效人脸） | ✅ 4xx/5xx |

### 关于 T4（最终一致性）
`CreateUser` + `AssociateFaces` 后，user 向量有几秒延迟才可被 `SearchUsersByImage` 检索到。若仅用 user 向量查重，连续快速上传同一人会漏判成新用户。**解决**：入库查重同时用 `SearchUsersByImage`（user 向量）+ `SearchFacesByImage`（face 向量，IndexFaces 后即时可查），任一命中即判重复。

---

## 7. 安全绑定流程（Token + AccountId↔AttemptId↔SessionId）

> 分支 `feature/session-binding-auth` 新增。用于生产级测试：Token 鉴权 + 会话绑定 +
> AttemptId 状态机（防盗用/防重放/防串改）。绑定存储默认内存，可换 DynamoDB。

### 流程
```
1. App 用现有 Token 调后端         → Authorization: Bearer <token>
2. 后端验 Token → AccountId
3. 后端 CreateFaceLivenessSession  → SessionId
4. 后端持久化绑定  AccountId ↔ AttemptId ↔ SessionId  (返回 attemptId)
5-6. App 从 Identity Pool 取临时凭证，调 StartFaceLivenessSession（Amplify 组件封装）
7. AWS 校验 IAM 权限 + SessionId 有效性
8. App 完成后回调后端（带 attemptId + sessionId + Token）
9. 后端再次校验绑定关系 → 通过才 GetFaceLivenessSessionResults
```

### 安全接口
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/secure/liveness/session` | 需 Bearer Token；创建会话并绑定，返回 attemptId/sessionId/accountId/state |
| POST | `/api/secure/liveness/attempt/{attemptId}/complete` | 需 Token + form `session_id`；校验绑定后取结果 + 1:N + 入库 |

### Demo Token（mock，见 `backend/auth.py`）
`demo-token-alice → acct-alice-001` · `demo-token-bob → acct-bob-002` · `demo-token-carol → acct-carol-003`

### curl 测试
```bash
# 无 token → 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/api/secure/liveness/session

# 有效 token → 200，返回 attemptId + sessionId
RESP=$(curl -s -X POST http://localhost:8000/api/secure/liveness/session \
  -H "Authorization: Bearer demo-token-alice"); echo "$RESP"

# 用错误账号（bob）完成 alice 的 attempt → 403 AccountId mismatch
# 用错误 sessionId → 403 SessionId mismatch
# 重复完成同一 attempt → 403 terminal（防重放）
```

### 已验证用例（feature 分支）
| # | 场景 | 预期 | 结果 |
|---|---|---|---|
| B1 | 无 token 创建会话 | 401 | ✅ |
| B2 | 无效 token | 401 | ✅ |
| B3 | 有效 token 创建 | 200 + attemptId + state=CREATED | ✅ |
| B4 | 错误账号完成 | 403 AccountId mismatch | ✅ |
| B5 | 错误 sessionId | 403 SessionId mismatch | ✅ |
| B6 | 未知 attemptId | 403 Unknown | ✅ |
| B7 | 重放（已完成再调） | 403 terminal | ✅ |
| B8 | 状态机非法转移 | BindingError | ✅ |
| B9 | 会话过期（TTL 180s） | 403 expired，状态→EXPIRED | ✅ |

自动化测试：`cd backend && pytest -q test_binding_auth.py`（11 passed）。
实测：上述 curl 针对真实 AWS `CreateFaceLivenessSession` 全部符合预期。

---

## 8. 阈值调优

| 变量 | 默认 | 说明 |
|---|---|---|
| `LIVENESS_CONFIDENCE_THRESHOLD` | 80 | 活体通过阈值，建议 ≥80 |
| `USER_MATCH_THRESHOLD` | 90 | 1:N 相似度阈值，查重建议 ≥90 降误配 |

调高查重阈值 → 更严格（减少误判为重复，但可能漏判）；调低 → 更宽松。按业务对误拒/误纳的容忍度调整。
