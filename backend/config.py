"""Application configuration loaded from environment variables."""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    liveness_s3_bucket: str = os.getenv("LIVENESS_S3_BUCKET", "")
    liveness_s3_prefix: str = os.getenv("LIVENESS_S3_PREFIX", "liveness-audit/")
    collection_id: str = os.getenv("REKOGNITION_COLLECTION_ID", "liveness-demo-collection")
    audit_images_limit: int = int(os.getenv("AUDIT_IMAGES_LIMIT", "2"))
    liveness_confidence_threshold: float = float(
        os.getenv("LIVENESS_CONFIDENCE_THRESHOLD", "80")
    )
    user_match_threshold: float = float(os.getenv("USER_MATCH_THRESHOLD", "90"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    cross_account_role_arn: str = os.getenv("CROSS_ACCOUNT_ROLE_ARN", "")


@lru_cache
def get_settings() -> Settings:
    return Settings()
