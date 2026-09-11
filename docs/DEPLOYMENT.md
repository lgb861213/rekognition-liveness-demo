# 部署指南（Deployment Guide）

本文档描述如何从零部署 Rekognition Face Liveness + 1:N 查重 Demo，涵盖基础设施（Terraform / CloudFormation）、后端、前端三部分。

---

## 0. 前置条件

| 依赖 | 版本 | 说明 |
|---|---|---|
| AWS 账号 | — | 需有 Rekognition / S3 / Cognito / IAM 权限 |
| AWS CLI | v2 | `aws configure` 配好凭证与默认区域 |
| Terraform | ≥ 1.5 | 方式 A 需要 |
| Python | ≥ 3.10 | 后端 |
| Node.js | ≥ 18 | 前端 |

> **区域选择**：推荐 `us-east-1`。约束：Face Liveness 要求 **S3 桶与 Rekognition 端点同账号同区域**；Cognito Identity Pool 也需与之同区域。

---

## 1. 部署基础设施（二选一）

部署内容：安全 S3 桶（禁公网 + 强制 TLS + SSE + 版本化 + 90 天生命周期）、Rekognition Collection、Cognito Identity Pool（guest 仅 `StartFaceLivenessSession`）、后端 IAM Role/Policy（最小权限）。

### 方式 A：Terraform

```bash
cd infra/terraform
terraform init
terraform apply \
  -var="aws_region=us-east-1" \
  -var="s3_bucket_name=<全局唯一桶名>" \
  -var="collection_id=liveness-demo-collection"
```

获取输出（后续配置要用）：

```bash
terraform output
# aws_region, s3_bucket_name, rekognition_collection_id,
# cognito_identity_pool_id, backend_role_arn
```

> **若 collection 已存在**（例如后端曾自动创建过）：先导入再 apply。
> ```bash
> terraform import \
>   -var="aws_region=us-east-1" \
>   -var="s3_bucket_name=<桶名>" \
>   -var="collection_id=liveness-demo-collection" \
>   aws_rekognition_collection.this liveness-demo-collection
> ```

### 方式 B：CloudFormation

```bash
cd infra/cloudformation
aws cloudformation deploy \
  --region us-east-1 \
  --template-file liveness-demo.yaml \
  --stack-name liveness-demo \
  --parameter-overrides ProjectName=liveness-demo CollectionId=liveness-demo-collection \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation describe-stacks --region us-east-1 \
  --stack-name liveness-demo --query "Stacks[0].Outputs" --output table
```

---

## 2. 部署后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `backend/.env`，用第 1 步的输出填写：

```dotenv
AWS_REGION=us-east-1
LIVENESS_S3_BUCKET=<s3_bucket_name>
REKOGNITION_COLLECTION_ID=<rekognition_collection_id>
LIVENESS_CONFIDENCE_THRESHOLD=80
USER_MATCH_THRESHOLD=90
AUDIT_IMAGES_LIMIT=2
FRONTEND_ORIGIN=http://localhost:3000
```

启动：

```bash
uvicorn main:app --reload --port 8000
```

- 健康检查：`curl http://localhost:8000/health`
- API 文档：`http://localhost:8000/docs`

**生产环境凭证**：本地开发用 `aws configure` 的用户凭证即可；生产把 IaC 输出的 `backend_role_arn` 附加到 ECS/EC2/Lambda，无需长期密钥。

---

## 3. 部署前端

```bash
cd frontend
npm install
cp .env.example .env
```

编辑 `frontend/.env`：

```dotenv
VITE_AWS_REGION=us-east-1
VITE_COGNITO_IDENTITY_POOL_ID=<cognito_identity_pool_id>
```

开发模式：

```bash
npm run dev          # http://localhost:3000（已代理 /api -> :8000）
```

生产构建：

```bash
npm run build        # 产物在 dist/
npm run preview      # 本地预览生产构建
```

> **HTTPS 要求**：`FaceLivenessDetector` 需摄像头权限。`localhost` 是安全上下文可直接用；部署到非 localhost 域名**必须启用 HTTPS**，否则浏览器禁用摄像头。

---

## 4. 部署架构建议（生产）

| 组件 | 本地 Demo | 生产建议 |
|---|---|---|
| 前端 | Vite dev server | S3 + CloudFront（静态托管，HTTPS） |
| 后端 | uvicorn --reload | ECS Fargate / Lambda + API Gateway，挂 `backend_role_arn` |
| 凭证 | 本地 AWS 用户 | IAM Role（无密钥） |
| 网络 | localhost | 后端置于私有子网，前端经 CDN |

---

## 5. 清理资源

```bash
# 方式 A：Terraform
cd infra/terraform && terraform destroy \
  -var="aws_region=us-east-1" \
  -var="s3_bucket_name=<桶名>" \
  -var="collection_id=liveness-demo-collection"

# 方式 B：CloudFormation
aws cloudformation delete-stack --region us-east-1 --stack-name liveness-demo
```

> S3 桶默认 `force_destroy=true`（TF）/ `DeletionPolicy: Delete`（CFN）便于 Demo 清理；生产请改为保留策略。Collection 删除后其中所有人脸/用户向量一并删除。

---

## 6. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `createSession failed: 500` + `NoSuchBucket` | S3 桶未创建或 `.env` 桶名不符 → 先跑 IaC，回填 `LIVENESS_S3_BUCKET` |
| 前端点活体无反应 / 摄像头报错 | `VITE_COGNITO_IDENTITY_POOL_ID` 未填真实值，或非 HTTPS 访问 |
| `ResourceAlreadyExistsException` (collection) | collection 已存在 → 见 §1 方式 A 的 import 步骤 |
| 改了 `.env` 前端不生效 | Vite 不热更新 `.env`，需重启 `npm run dev` |
| 跨账号 1:N | 后端设 `CROSS_ACCOUNT_ROLE_ARN`，AssumeRole 到中心查重账号（见 README §7） |
