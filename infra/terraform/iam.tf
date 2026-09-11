# IAM role + policy for the backend API (attach to your EC2/ECS/Lambda, or use
# the inline policy JSON directly for local dev credentials).

data "aws_iam_policy_document" "backend_permissions" {
  statement {
    sid    = "FaceLiveness"
    effect = "Allow"
    actions = [
      "rekognition:CreateFaceLivenessSession",
      "rekognition:GetFaceLivenessSessionResults",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "CollectionAndSearch"
    effect = "Allow"
    actions = [
      "rekognition:CreateCollection",
      "rekognition:DescribeCollection",
      "rekognition:IndexFaces",
      "rekognition:SearchUsersByImage",
      "rekognition:SearchUsers",
      "rekognition:SearchFacesByImage",
      "rekognition:CreateUser",
      "rekognition:AssociateFaces",
      "rekognition:DeleteUser",
      "rekognition:DeleteFaces",
      "rekognition:ListUsers",
      "rekognition:ListFaces",
    ]
    resources = [aws_rekognition_collection.this.arn]
  }

  # Read reference/audit images that Rekognition writes into the bucket.
  statement {
    sid       = "ReadLivenessImages"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.liveness.arn, "${aws_s3_bucket.liveness.arn}/*"]
  }
}

resource "aws_iam_policy" "backend" {
  name   = "${var.project_name}-backend-policy"
  policy = data.aws_iam_policy_document.backend_permissions.json
}

# Role assumable by ECS tasks / EC2 (adjust principal for your compute).
data "aws_iam_policy_document" "backend_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com", "ec2.amazonaws.com", "lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backend" {
  name               = "${var.project_name}-backend-role"
  assume_role_policy = data.aws_iam_policy_document.backend_assume.json
}

resource "aws_iam_role_policy_attachment" "backend" {
  role       = aws_iam_role.backend.name
  policy_arn = aws_iam_policy.backend.arn
}

# Grant Rekognition Face Liveness permission to write output images into the
# bucket. Face Liveness writes as the calling account, so the backend role's
# S3 read + the account owning the bucket is sufficient; no separate bucket
# policy for a service principal is required for same-account output.
