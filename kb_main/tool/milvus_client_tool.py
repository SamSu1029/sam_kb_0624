import socket
from urllib.parse import urlparse

from pymilvus import MilvusClient

from kb_main.config.config import MilvusConfig
from kb_main.tool.logger import logger

milvus_client=None

def _check_reachable(url: str, timeout: int = 5):
    """
    连接预检：用 socket 探测目标服务是否可达
    :param url: 服务地址，如 http://192.168.1.100:19530
    :param timeout: 连接超时秒数
    """
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        logger.info(f"Milvus 连通性预检通过: {host}:{port}")
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        raise ConnectionError(f"Milvus 不可达: {host}:{port}, 原因: {e}") from e
    finally:
        sock.close()


def get_milvus_client():
    global milvus_client
    if not milvus_client:
        try:
            _check_reachable(MilvusConfig.milvus_url, timeout=5)
            milvus_client = MilvusClient(
                uri=MilvusConfig.milvus_url,
                timeout=30,
            )
        except Exception as e:
            logger.error(f"milvus_client创建失败: {e}")
            raise e
    return milvus_client

if __name__ == "__main__":
    get_milvus_client()