"""AWS client factories.

Provides a Rekognition client (optionally in a cross-account "dedup" account via
STS AssumeRole) and an S3 client. Face Liveness requires the S3 bucket to live in
the SAME account and SAME region as the Rekognition endpoint, so the S3 client
always uses local credentials.
"""
import boto3

from config import get_settings

_settings = get_settings()


def _assumed_credentials(role_arn: str) -> dict:
    sts = boto3.client("sts", region_name=_settings.aws_region)
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName="rekognition-dedup")
    c = resp["Credentials"]
    return {
        "aws_access_key_id": c["AccessKeyId"],
        "aws_secret_access_key": c["SecretAccessKey"],
        "aws_session_token": c["SessionToken"],
    }


def rekognition_client():
    """Rekognition client. Uses cross-account role if CROSS_ACCOUNT_ROLE_ARN set."""
    if _settings.cross_account_role_arn:
        creds = _assumed_credentials(_settings.cross_account_role_arn)
        return boto3.client("rekognition", region_name=_settings.aws_region, **creds)
    return boto3.client("rekognition", region_name=_settings.aws_region)


def s3_client():
    return boto3.client("s3", region_name=_settings.aws_region)
