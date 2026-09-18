import json

from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.bgem3_client_tool import get_bge_m3_embedding
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger


class NodeBGEEmbedding(NodeBase):
    """
    混合向量化节点：使用 BGE-M3 模型将文本转换为向量
    """

    name = "node_bge_embedding"

    def process(self, state: ImportGraphState):
        chunks = state.get("chunks", "")
        if not chunks:
            logger.error("chunks不能为空")
            raise ValueError("chunks不能为空")

        for i in range(0, len(chunks), 3):
            chunk_k_list = chunks[i : i + 3]
            chunk_k_content_list = [
                f"{chunk.get('item_name')}{chunk.get('content')}"
                for chunk in chunk_k_list
            ]

            embedding = get_bge_m3_embedding(chunk_k_content_list)
            for idx, chunk in enumerate(chunk_k_list):
                chunk["dense_vector"] = embedding.get("dense")[idx]
                chunk["sparse_vector"] = embedding.get("sparse")[idx]


        # 备份chunks后期下个节点测试使用
        with open(r"D:\data\output\hak180产品安全手册\embedding_chunks.json","w",encoding="utf-8") as f:
            # f.write(json.dumps(chunks,ensure_ascii=False))
            f.write(json_format(chunks))


        return {"chunks":chunks}


if __name__ == "__main__":
    node = NodeBGEEmbedding()

    with open(
        r"D:\data\output\hak180产品安全手册\item_name_chunks.json",
        "r",
        encoding="utf-8",
    ) as f:
        chunks = json.load(f)
    state = {"chunks": chunks}
    res = node(state)
    logger.info(json_format(res))
