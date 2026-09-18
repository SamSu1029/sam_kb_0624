from typing import List

from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from torch import embedding

from kb_main.config.config import EmbeddingConfig
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger

bge_m3_model = None


def get_bge_m3_model():
    global bge_m3_model
    if not bge_m3_model:
        bge_m3_model = BGEM3EmbeddingFunction(
            model_name=EmbeddingConfig.bge_m3_path,
            device=EmbeddingConfig.bge_device,
            use_fp16=EmbeddingConfig.bge_fp16,
        )
    return bge_m3_model


def get_bge_m3_embedding(texts: List[str]):
    bge_m3_model = get_bge_m3_model()
    embedding = bge_m3_model.encode_documents(texts)
    # print(embedding)
    # print(embedding.get("dense"),type(embedding.get("dense"))) # <class 'list'>
    # print(embedding.get("dense")[0],type(embedding.get("dense")[0])) #<class 'numpy.ndarray'>
    # print(embedding.get("dense")[0][0],type(embedding.get("dense")[0][0])) #<class 'numpy.float16'>
    # print(embedding.get("dense",[])[0].tolist()[0],type(embedding.get("dense",[])[0].tolist()[0])) # <class 'float'>

    # print(embedding.get("sparse"),type(embedding.get("sparse"))) # <class 'scipy.sparse._csr.csr_array'>
    # print(embedding.get("sparse").__dict__) #'_shape': (2, 250002) embedding.get("sparse")可遍历出每个对象
    """CSR
    indices [     6,   6128,  16363,      6,   1516, 243972]
    indptr  [0, 3, 6]
    data    [0.05813599, 0.22033691, 0.35668945, 0.03918457, 0.28320312, 0.26513672]
    """

    return {
        "dense": [ dense_item.tolist() for dense_item in embedding.get("dense", []) ],  # [[阿宝],[驴本]]
        "sparse":[ dict(zip(sparse_item.indices.tolist(),sparse_item.data.tolist())) for sparse_item in embedding.get("sparse")] #[{indices:data},{}]
    }


if __name__ == "__main__":
    embedding=get_bge_m3_embedding(["阿宝", "驴本"])
    logger.info(json_format(embedding))
"""
{
"dense": [
        [],[]
    ],

"sparse": [
        {
            "6": 0.058135986328125,
            "6128": 0.2203369140625,
            "16363": 0.356689453125
        },
        {
            "6": 0.0391845703125,
            "1516": 0.283203125,
            "243972": 0.26513671875
        }
    ]
}
"""