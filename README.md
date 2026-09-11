# Rekognition Face Liveness + 1:N Collection Demo

一个可测试验证的完整 Demo：**实时活体检测（Face Liveness）** + **人脸模板托管与 1:N 查重（Rekognition Collection / User Vectors）** + **同区域 S3 存储参考图/审计图**。支持 **Terraform** 或 **CloudFormation** 一键部署基础设施。

> 架构图：`docs/architecture.drawio`（用 [draw.io](https://app.diagrams.net/) 打开）

## 文档导航

| 文档 | 内容 |
|---|---|
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | 部署指南（Terraform / CloudFormation / 后端 / 前端 / 清理 / FAQ） |
| [docs/TESTING.md](docs/TESTING.md) | 测试验证指南（API、UI 操作、curl、已验证用例） |
| [docs/IAM_SETUP.md](docs/IAM_SETUP.md) | 本地测试 IAM 用户与最小权限（aws configure 配置） |
| [docs/architecture.drawio](docs/architecture.drawio) | 架构与数据流图 |

---

## 1. 需求 → 方案映射

| 核心需求 | 落地方式 |
|---|---|
| 实时活体检测 | Rekognition Face Liveness：`CreateFaceLivenessSession` → 前端 Amplify `FaceLivenessDetector`（`StartFaceLivenessSession` WebSocket）→ `GetFaceLivenessSessionResults` |
| 人脸模板托管 | Rekognition Collection + `IndexFaces`（face vector），`CreateUser` + `AssociateFaces`（user vector，检索更准） |
| 跨账号 1:N 查重 | `SearchUsersByImage`。Demo 用**集中式单 Collection**；跨账号见 §7 |
| 数据合规 / 数据驻留 | 全部资源部署在 **us-east-1**（美国境内），参考图/审计图落到**同账号同区域**的 S3，**不跨境到中国大陆**，不经 OSS |
| 最省成本 | 纯按量计费，无固定实例；活体流式 $0.015/次、图像 API $0.001/图、向量存储 $0.01/1000/月 |

### 为什么选 us-east-1
- 数据驻留：参考图/审计图/生物特征向量留在美国境内。Face Liveness 强制要求 **S3 桶与 Rekognition 端点同账号同区域**。
- 成本：`us-east-1` 是 Rekognition 定价最低、功能最全（Liveness + Collections + User Vectors）的区域之一。
- 同区读写：`IndexFaces`/`SearchUsersByImage` 直接读同区 S3，降延迟、减少跨云传输与失败点。

---

## 2. 目录结构

```
rekognition-liveness-demo/
├── backend/                  # FastAPI 后端
│   ├── main.py               # 路由
│   ├── rekognition_service.py# Liveness + 1:N 业务逻辑
│   ├── aws_clients.py        # boto3 客户端（含可选跨账号 AssumeRole）
│   ├── config.py schemas.py
│   ├── requirements.txt .env.example
├── frontend/                 # Vite + React + Amplify FaceLivenessDetector
│   ├── src/{main.jsx,App.jsx,api.js,amplifyConfig.js}
│   ├── package.json vite.config.js index.html .env.example
├── infra/
│   ├── terraform/            # S3 / Collection / Cognito / IAM
│   └── cloudformation/liveness-demo.yaml
└── docs/architecture.drawio
```

---

## 3. 前置条件

- AWS 账号 + 已配置凭证（`aws configure`），有 Rekognition/S3/Cognito/IAM 权限
- Python 3.10+（后端），Node 18+（前端）
- Terraform ≥ 1.5 **或** AWS CLI（用于 CloudFormation）

---

## 4. 部署基础设施（二选一）

### 方式 A：Terraform

```bash
cd infra/terraform
terraform init
terraform apply -var="aws_region=us-east-1"
```

记录输出：

```bash
terraform output
# s3_bucket_name, rekognition_collection_id, cognito_identity_pool_id, backend_role_arn
```

### 方式 B：CloudFormation

```bash
cd infra/cloudformation
aws cloudformation deploy \
  --region us-east-1 \
  --template-file liveness-demo.yaml \
  --stack-name liveness-demo \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation describe-stacks --region us-east-1 \
  --stack-name liveness-demo --query "Stacks[0].Outputs"
```

> 两套 IaC 产出等价资源：安全的 S3 桶（禁公网 + 强制 TLS + SSE + 版本化 + 90 天生命周期）、Rekognition Collection、Cognito Identity Pool（guest 仅 `StartFaceLivenessSession`）、后端 IAM Role/Policy（最小权限）。

---

## 5. 运行后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 用 IaC 输出填写 .env：
#   AWS_REGION=us-east-1
#   LIVENESS_S3_BUCKET=<s3_bucket_name>
#   REKOGNITION_COLLECTION_ID=<rekognition_collection_id>
uvicorn main:app --reload --port 8000
```

- 健康检查：`curl http://localhost:8000/health`
- API 文档：`http://localhost:8000/docs`

> 本地开发使用你自己的 AWS 凭证即可；生产环境把 IaC 输出的 `backend_role_arn` 附加到 ECS/EC2/Lambda 计算上。

---

## 6. 运行前端

```bash
cd frontend
npm install
cp .env.example .env
# 填写：
#   VITE_AWS_REGION=us-east-1
#   VITE_COGNITO_IDENTITY_POOL_ID=<cognito_identity_pool_id>
npm run dev      # http://localhost:3000  (已代理 /api -> :8000)
```

> **HTTPS/摄像头**：`FaceLivenessDetector` 需要摄像头权限。`localhost` 被浏览器视为安全上下文可直接用；部署到非 localhost 域名时必须启用 **HTTPS**。

---

## 7. 测试验证流程
### 登录（Token 鉴权 · 所有功能需先登录）
打开 `http://localhost:3000` 会先看到**登录页**——无有效 Token 无法访问任何功能。
Demo 内置 3 个 mock Token（登录页有快捷按钮，见 `backend/auth.py`）：

| 登录框填写的 Token | 映射业务 AccountId |
|---|---|
| `demo-token-alice` | `acct-alice-001` |
| `demo-token-bob` | `acct-bob-002` |
| `demo-token-carol` | `acct-carol-003` |

> 乱填 Token → 401 拒绝。生产环境把 `auth.py` 的 `verify_token()` 换成真实 JWT/OIDC 验签即可。

### 活体 + 1:N（端到端，需摄像头，安全绑定流程）
1. 用某个 Token 登录（如 `demo-token-alice`）。
2. 点「开始活体检测」→ 后端 `POST /api/secure/liveness/session`：验 Token→AccountId →
   `CreateFaceLivenessSession` → 持久化绑定 `AccountId↔AttemptId↔SessionId`，返回 attemptId。
3. 完成头部/光照挑战。
4. 完成回调 `POST /api/secure/liveness/attempt/{attemptId}/complete`：后端**二次校验绑定关系**
   （账号+attempt+session 一致、未过期、未重放）→ 通过才 `GetFaceLivenessSessionResults` →
   1:N 查重 → 唯一则入库。

### Collection 1:N（图片上传，无需摄像头，快速回归）
- 登录后，右侧面板「入库」上传人脸图 → **先 1:N 查重，唯一才入库**（返回 userId/faceId 或「已存在」）。
- 「1:N 查重」上传同一人另一张图 → 返回匹配的 `userId` 与相似度。
- 命令行等价（**需带 Token**）：
  ```bash
  TOKEN="demo-token-alice"
  curl -H "Authorization: Bearer $TOKEN" -F "file=@alice1.jpg" http://localhost:8000/api/collection/enroll
  curl -H "Authorization: Bearer $TOKEN" -F "file=@alice2.jpg" http://localhost:8000/api/collection/search
  ```

### 阈值
- 活体通过阈值 `LIVENESS_CONFIDENCE_THRESHOLD`（默认 80，建议 ≥80）。
- 1:N 相似度阈值 `USER_MATCH_THRESHOLD`（默认 90，查重建议 ≥90 以降误配）。

### 跨账号 1:N 扩展（集中式）
- 在**中心查重账号**创建一个 IAM Role（信任各业务账号），授予 Collection 相关权限。
- 各业务账号后端设置 `CROSS_ACCOUNT_ROLE_ARN=arn:aws:iam::<中心账号>:role/RekognitionDedupRole`。
- 后端 `aws_clients.py` 会自动 `AssumeRole` 后调用中心账号里的同一个 Collection，实现跨账号统一查重。

---

## 8. 成本估算（us-east-1，按量付费，ON DEMAND）

单价（数据来自 AWS Pricing API，2026-06 生效）：

| 项目 | 单价 |
|---|---|
| Face Liveness 流式调用 | $0.015 / 次（0–500K/月档） |
| IndexFaces / SearchUsersByImage（图像 API） | $0.001 / 图（0–1M/月档） |
| Face vector 存储 | $0.01 / 1000 faces / 月 |
| User vector 存储 | $0.01 / 1000 users / 月 |
| S3 标准存储 | ~$0.023 / GB / 月 |

**示例：每月 10,000 次验证（每次 = 1 活体 + 1 查重；假设 30% 为新用户入库），累计 5 万用户在库**

| 项目 | 计算 | 金额 |
|---|---|---|
| 活体检测 | 10,000 × $0.015 | **$150.00** |
| 1:N 查重（SearchUsersByImage） | 10,000 × $0.001 | **$10.00** |
| 新用户入库（IndexFaces，30%） | 3,000 × $0.001 | **$3.00** |
| User vector 存储 | 50,000 / 1000 × $0.01 | **$0.50** |
| Face vector 存储 | 50,000 / 1000 × $0.01 | **$0.50** |
| S3 审计图（~2 张/次 ×10K ×100KB ≈ 2GB，90 天生命周期） | ~2 GB × $0.023 | **~$0.05** |
| **合计** | | **≈ $164 / 月** |

> 说明与排除项：不含前端托管、后端计算（ECS/Lambda）、数据传输、KMS、Cognito（本用途免费额度内）。价格随 AWS 调整而变，请以 [AWS 官方定价](https://aws.amazon.com/rekognition/pricing/) 与 AWS Pricing Calculator 为准。活体调用量 >500K/月 会进入更低单价档（$0.0125 / $0.010）。

---

## 9. 安全与合规要点

- S3：禁公网访问、强制 TLS（`aws:SecureTransport=false` 拒绝）、SSE-S3 加密、版本化、审计图 90 天过期。可按需改为 SSE-KMS。
- Cognito guest 角色仅授予 `rekognition:StartFaceLivenessSession`（最小权限）。
- 后端 IAM Policy 的 Collection 操作按资源 ARN 限定；活体 API 需 `Resource:*`（服务限制）。
- 生物特征数据全程留在 `us-east-1`，不跨境。
- `isLive` 授权判定必须在后端完成，前端返回值不可作为鉴权依据（AWS 官方要求）。
- **Token 鉴权**：所有业务端点（活体、1:N、用户管理）均需 `Authorization: Bearer <token>`，仅 `/health` 公开；未授权一律 401。Demo 用 mock token，生产替换 `backend/auth.py` 的 `verify_token()` 为真实 JWT/OIDC 验签。
- **会话绑定防盗用/防重放**：`POST /api/secure/liveness/session` 持久化 `AccountId↔AttemptId↔SessionId`；取结果前二次校验该绑定，并用 AttemptId 状态机（CREATED→COMPLETED/FAILED/EXPIRED）拒绝重放、拒绝跨账号越权、TTL 180s 过期（对齐 AWS SessionId 3 分钟）。见 `backend/binding_store.py`，生产可换 DynamoDB（已含映射说明）。

---

## 10. 清理

```bash
# Terraform
cd infra/terraform && terraform destroy

# CloudFormation
aws cloudformation delete-stack --region us-east-1 --stack-name liveness-demo
```

> S3 桶默认 `force_destroy=true`（Terraform）/ `DeletionPolicy: Delete`（CFN）方便 Demo 清理；生产请改为保留。

---

## 附：验证状态

- 后端：`import main` 通过，10 条路由注册正常（FastAPI）。
- Terraform：`terraform validate` = Success。
- CloudFormation：cfn-lint = valid，0 错误。
- 前端：代码完整；需 `npm install` 后 `npm run dev` 运行（活体检测需真实摄像头，无法在无头环境自动化验证）。
