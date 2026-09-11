variable "aws_region" {
  description = "Region for Rekognition, S3, and Cognito. MUST be identical across all three."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Prefix for resource names."
  type        = string
  default     = "liveness-demo"
}

variable "collection_id" {
  description = "Rekognition collection ID for 1:N user vectors."
  type        = string
  default     = "liveness-demo-collection"
}

variable "s3_bucket_name" {
  description = "Globally-unique S3 bucket name for liveness reference/audit images. Leave empty to auto-generate."
  type        = string
  default     = ""
}

variable "force_destroy_bucket" {
  description = "Allow Terraform to delete a non-empty bucket on destroy (demo convenience)."
  type        = bool
  default     = true
}
