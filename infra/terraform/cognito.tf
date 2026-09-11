# Cognito Identity Pool used by the frontend FaceLivenessDetector component.
# Guest (unauthenticated) identities are enabled solely so the browser can sign
# the StartFaceLivenessSession streaming request to Rekognition.

resource "aws_cognito_identity_pool" "liveness" {
  identity_pool_name               = "${var.project_name}-idpool"
  allow_unauthenticated_identities = true
  allow_classic_flow               = false
}

data "aws_iam_policy_document" "cognito_unauth_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = ["cognito-identity.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "cognito-identity.amazonaws.com:aud"
      values   = [aws_cognito_identity_pool.liveness.id]
    }
    condition {
      test     = "ForAnyValue:StringLike"
      variable = "cognito-identity.amazonaws.com:amr"
      values   = ["unauthenticated"]
    }
  }
}

resource "aws_iam_role" "cognito_unauth" {
  name               = "${var.project_name}-cognito-unauth"
  assume_role_policy = data.aws_iam_policy_document.cognito_unauth_assume.json
}

# Least-privilege: guests may ONLY start a liveness streaming session.
resource "aws_iam_role_policy" "cognito_unauth_liveness" {
  name = "StartFaceLivenessSession"
  role = aws_iam_role.cognito_unauth.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "rekognition:StartFaceLivenessSession"
        Resource = "*"
      }
    ]
  })
}

resource "aws_cognito_identity_pool_roles_attachment" "liveness" {
  identity_pool_id = aws_cognito_identity_pool.liveness.id
  roles = {
    unauthenticated = aws_iam_role.cognito_unauth.arn
  }
}
