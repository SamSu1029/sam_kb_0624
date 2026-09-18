"""
    @Author:Sam
    @Time:2026/9/6
    @Desc:
"""
from dotenv import load_dotenv
import os

env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.env"))
load_dotenv(dotenv_path=env_path, override=True)

def get_required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"未找到该环境变量: {name}")
    return value


class MineruConfig:
    mineru_token =get_required_env("MINERU_TOKEN")
    mineru_base_url = get_required_env("MINERU_BASE_URL")


class LLMConfig:
    openai_api_key = get_required_env("OPENAI_API_KEY")
    openai_api_base = get_required_env("OPENAI_API_BASE")
    llm_default_model = get_required_env("LLM_DEFAULT_MODEL")
    llm_default_temperature = float(get_required_env("LLM_DEFAULT_TEMPERATURE"))
    vl_model = get_required_env("VL_MODEL")
    item_model = get_required_env("ITEM_MODEL")


class MinIoConfig:
    minio_endpoint = get_required_env("MINIO_ENDPOINT")
    minio_access_key = get_required_env("MINIO_ACCESS_KEY")
    minio_secret_key = get_required_env("MINIO_SECRET_KEY")
    minio_bucket_name = get_required_env("MINIO_BUCKET_NAME")
    minio_img_dir = get_required_env("MINIO_IMG_DIR")


# config/config.py
class EmbeddingConfig:
    bge_m3_path=get_required_env("BGE_M3_PATH")
    bge_m3=get_required_env("BGE_M3")
    bge_device=get_required_env("BGE_DEVICE")
    # 特殊处理：将.env中的1/0转为布尔值，兼容常见的数字/字符串格式
    bge_fp16=get_required_env("BGE_FP16") in ("1", "True", "true", 1)

class MilvusConfig:
    milvus_url=get_required_env("MILVUS_URL")
    chunks_collection=get_required_env("CHUNKS_COLLECTION")
    item_name_collection=get_required_env("ITEM_NAME_COLLECTION")


class MongoConfig:
    mongo_url=get_required_env("MONGO_URL")
    mongo_db_name=get_required_env("MONGO_DB_NAME")