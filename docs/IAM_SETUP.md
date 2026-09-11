# 本地测试 IAM 用户与最小权限（Local Test IAM）

本文档说明如何为**后端本地测试**创建一个最小权限 IAM 用户，并配置到 `aws configure`。

> 适用范围：给后端 API（FastAPI）本地运行时调用 Rekognition / 读取 S3 使用。
> **不含**基础设施部署权限（创建 S3/Cognito/IAM 由 Terraform/CloudFormation 用你的管理员或部署角色完成）。

---

## 1. 后端实际调用的 API → 所需权限

| 功能 | boto3 调用 | IAM Action | 资源范围 |
|---|---|---|---|
| 创建活体会话 | `create_face_liveness_session` | `rekognition:CreateFaceLivenessSession` | `*`（不支持资源级限制） |
| 获取活体结果 | `get_face_liveness_session_results` | `rekognition:GetFaceLivenessSessionResults` | `*` |
| 建集合（首启自动） | `create_collection` | `rekognition:CreateCollection` | collection ARN |
| 查集合信息 | `describe_collection` | `rekognition:DescribeCollection` | collection ARN |
| 人脸入库 | `index_faces` | `rekognition:IndexFaces` | collection ARN |
| 1:N 查重（user） | `search_users_by_image` | `rekognition:SearchUsersByImage` | collection ARN |
| 1:N 查重（face） | `search_faces_by_image` | `rekognition:SearchFacesByImage` | collection ARN |
| 建用户 | `create_user` | `rekognition:CreateUser` | collection ARN |
| 关联人脸 | `associate_faces` | `rekognition:AssociateFaces` | collection ARN |
| 删用户 | `delete_user` | `rekognition:DeleteUser` | collection ARN |
| 删人脸 | `delete_faces` | `rekognition:DeleteFaces` | collection ARN |
| 列用户 | `list_users` | `rekognition:ListUsers` | collection ARN |
| 列人脸 | `list_faces` | `rekognition:ListFaces` | collection ARN |
| 读参考图/审计图 | `get_object` | `s3:GetObject` | bucket/* |
| 列桶对象 | （隐式） | `s3:ListBucket` | bucket |

> 说明：Face Liveness 的两个 action 是 AWS 限制只能用 `Resource: "*"`；集合类 action 可精确限定到 collection ARN。这与 `infra/terraform/iam.tf`、CloudFormation 模板中给后端角色的权限**完全一致**。

策略 JSON 见：[`infra/iam/backend-test-user-policy.json`](../infra/iam/backend-test-user-policy.json)（把 `ACCOUNT_ID`、`YOUR_BUCKET_NAME` 替换成你的实际值）。

---

## 2. 创建 IAM 用户（AWS CLI，需管理员权限执行一次）

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
BUCKET=my-rekognition-liveness-demo-us-east-1
COLLECTION=liveness-demo-collection
USER=liveness-demo-backend-test

# 1) 生成策略文件（替换占位符）
sed -e "s/ACCOUNT_ID/${ACCOUNT_ID}/g" \
    -e "s/YOUR_BUCKET_NAME/${BUCKET}/g" \
    infra/iam/backend-test-user-policy.json > /tmp/policy.json

# 2) 创建用户
aws iam create-user --user-name "${USER}"

# 3) 绑定内联最小权限策略
aws iam put-user-policy \
  --user-name "${USER}" \
  --policy-name liveness-demo-backend \
  --policy-document file:///tmp/policy.json

# 4) 生成访问密钥（记下 AccessKeyId / SecretAccessKey）
aws iam create-access-key --user-name "${USER}"
```

> 如果 collection ID 或桶名与默认不同，先改上面的变量再执行。

---

## 3. 配置到 aws configure

推荐用**独立 profile**，避免污染默认凭证：

```bash
aws configure --profile liveness-demo
# AWS Access Key ID     : <上一步的 AccessKeyId>
# AWS Secret Access Key : <上一步的 SecretAccessKey>
# Default region name   : us-east-1
# Default output format  : json
```

启动后端时指定该 profile：

```bash
cd backend
export AWS_PROFILE=liveness-demo      # 或写进 shell 环境
source .venv/bin/activate
uvicorn main:app --reload --port 8000
```

> boto3 会自动读取 `AWS_PROFILE`。也可用默认 profile（`aws configure` 不加 `--profile`），则无需 export。

---

## 4. 验证权限是否够用

```bash
# 起后端后：
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/api/liveness/session   # 需要 S3 桶已存在
curl -s http://localhost:8000/api/collection/stats
```

若报 `AccessDenied`，对照 §1 表格检查缺失的 action；若报 `NoSuchBucket`，先用 IaC 建好 S3 桶并核对 `.env` 的 `LIVENESS_S3_BUCKET`。

---

## 5. 跨账号 1:N（可选）

若使用集中式查重账号（`.env` 设 `CROSS_ACCOUNT_ROLE_ARN`），需给本用户额外加：

```json
{
  "Sid": "AssumeDedupRole",
  "Effect": "Allow",
  "Action": "sts:AssumeRole",
  "Resource": "arn:aws:iam::CENTRAL_ACCOUNT_ID:role/RekognitionDedupRole"
}
```

并在中心账号的该 Role 上附加 §1 中的 Collection 相关权限，信任本账号。

---

## 6. 安全建议

- 测试用户密钥**不要提交到 git**（`.env`、密钥文件已在 `.gitignore` 中）。
- 测试结束后可删除用户：
  ```bash
  aws iam delete-access-key --user-name "${USER}" --access-key-id <KEYID>
  aws iam delete-user-policy --user-name "${USER}" --policy-name liveness-demo-backend
  aws iam delete-user --user-name "${USER}"
  ```
- 生产环境**不要用 IAM 用户长期密钥**，改用附加到 ECS/EC2/Lambda 的 IAM Role（IaC 已输出 `backend_role_arn`）。
