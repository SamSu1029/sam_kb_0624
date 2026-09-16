
from typing import List

from kb_main.config.config import EmbeddingConfig
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger

from pymilvus.model.hybrid import BGEM3EmbeddingFunction


bge_m3_model = None



def get_bge_m3_model():
    global bge_m3_model
    if not bge_m3_model:
        bge_m3_model = BGEM3EmbeddingFunction(
            model_name=EmbeddingConfig.bge_m3_path,
            devices=EmbeddingConfig.bge_device,
            use_fp16=EmbeddingConfig.bge_fp16,
        )
    return bge_m3_model


def get_bge_m3_embedding(texts: List[str]):
    bge_m3_model = get_bge_m3_model()
    embedding = bge_m3_model.encode_documents(texts)
    # print(embedding)

    # print(embedding.get("dense"))
    # print(embedding.get("sparse"))

    # 打印查看稠密向量的本质类型
    # for dense_item in embedding.get("dense"):
    #     print(dense_item,type(dense_item))

    # for sparse_item in embedding.get("sparse"):
    #     print(sparse_item,type(sparse_item))
    #     # print(sparse_item.__dict__)
        

    # return {
    #     "dense":[list([float(item) for item in dense_item]) for dense_item in embedding.get("dense")],
    #     "sparse":[
    #         dict(zip(
    #             [int(indice) for indice in sparse_item.indices],
    #             [float(data) for data in sparse_item.data]
    #         ))
    #         for sparse_item in embedding.get("sparse")
    #     ]
    # }

    return {
        "dense": [dense_item.tolist() for dense_item in embedding.get("dense")],
        "sparse": [
            dict(zip(sparse_item.indices.tolist(),sparse_item.data.tolist()))
            for sparse_item in embedding.get("sparse")
        ]
    }


if __name__ == '__main__':
    texts = ["hello world", "hello milvus"]
    result = get_bge_m3_embedding(texts)
    # logger.info(json_format(result))