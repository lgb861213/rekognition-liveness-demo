output "aws_region" {
  value = var.aws_region
}

output "s3_bucket_name" {
  description = "Set this as LIVENESS_S3_BUCKET in the backend .env"
  value       = aws_s3_bucket.liveness.id
}

output "rekognition_collection_id" {
  description = "Set this as REKOGNITION_COLLECTION_ID in the backend .env"
  value       = aws_rekognition_collection.this.collection_id
}

output "cognito_identity_pool_id" {
  description = "Set this as VITE_COGNITO_IDENTITY_POOL_ID in the frontend .env"
  value       = aws_cognito_identity_pool.liveness.id
}

output "backend_role_arn" {
  description = "Attach to your backend compute (ECS/EC2/Lambda)."
  value       = aws_iam_role.backend.arn
}

output "backend_policy_arn" {
  value = aws_iam_policy.backend.arn
}
