import json

from minio import Minio

from kb_main.config.config import MinIoConfig
from kb_main.tool.logger import logger

minio_client = None
def get_minio_client():
    global minio_client
    if not minio_client:

        try:
            minio_client = Minio(
                endpoint=MinIoConfig.minio_endpoint,
                access_key=MinIoConfig.minio_access_key,
                secret_key=MinIoConfig.minio_secret_key,
                secure=False
            )
            bucket_name = MinIoConfig.minio_bucket_name
            if not minio_client.bucket_exists(bucket_name=bucket_name):
                minio_client.make_bucket(bucket_name=bucket_name)

            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                        "Resource": f"arn:aws:s3:::{bucket_name}",
                    },
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": "*"},
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{bucket_name}/*",
                    },
                ],
            }
            minio_client.set_bucket_policy(bucket_name=bucket_name, policy=json.dumps(policy))
        except Exception as e:
            logger.error(f"minio初始化客户端失败{e}")
            raise e
    return minio_client

if __name__ == "__main__":
    get_minio_client()
    print("****")

