"""
Cloudflare R2 Storage for Copilot Documents
"""
import uuid
from typing import Optional

import boto3
from botocore.config import Config

from app.core.config import settings


def get_r2_client():
    """
    Get an S3-compatible client for Cloudflare R2.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


async def upload_to_r2(
    file_content: bytes,
    filename: str,
    content_type: str = "application/octet-stream",
    folder: str = "copilot-documents",
) -> str:
    """
    Upload a file to Cloudflare R2 storage.

    Args:
        file_content: File bytes to upload
        filename: Name for the file in storage
        content_type: MIME type of the file
        folder: Subfolder in the bucket

    Returns:
        Public URL of the uploaded file
    """
    client = get_r2_client()
    bucket = settings.R2_BUCKET_NAME

    # Create object key with folder
    object_key = f"{folder}/{filename}"

    # Upload file
    client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=file_content,
        ContentType=content_type,
    )

    # Return public URL
    public_url = f"{settings.R2_PUBLIC_URL}/{object_key}"
    return public_url


async def download_from_r2(
    filename: str,
    folder: str = "copilot-documents",
) -> bytes:
    """
    Download a file from Cloudflare R2 storage.

    Args:
        filename: Name of the file in storage
        folder: Subfolder in the bucket

    Returns:
        File content as bytes
    """
    client = get_r2_client()
    bucket = settings.R2_BUCKET_NAME

    object_key = f"{folder}/{filename}"

    response = client.get_object(Bucket=bucket, Key=object_key)
    return response["Body"].read()


async def delete_from_r2(
    filename: str,
    folder: str = "copilot-documents",
) -> bool:
    """
    Delete a file from Cloudflare R2 storage.

    Args:
        filename: Name of the file in storage
        folder: Subfolder in the bucket

    Returns:
        True if deletion was successful
    """
    client = get_r2_client()
    bucket = settings.R2_BUCKET_NAME

    object_key = f"{folder}/{filename}"

    client.delete_object(Bucket=bucket, Key=object_key)
    return True


async def generate_presigned_url(
    filename: str,
    folder: str = "copilot-documents",
    expiration: int = 3600,
) -> str:
    """
    Generate a presigned URL for temporary access to a file.

    Args:
        filename: Name of the file in storage
        folder: Subfolder in the bucket
        expiration: URL expiration time in seconds (default 1 hour)

    Returns:
        Presigned URL string
    """
    client = get_r2_client()
    bucket = settings.R2_BUCKET_NAME

    object_key = f"{folder}/{filename}"

    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=expiration,
    )
    return url
