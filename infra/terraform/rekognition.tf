# Rekognition collection storing user/face vectors for 1:N de-duplication.
resource "aws_rekognition_collection" "this" {
  collection_id = var.collection_id

  tags = {
    Project = var.project_name
  }
}
