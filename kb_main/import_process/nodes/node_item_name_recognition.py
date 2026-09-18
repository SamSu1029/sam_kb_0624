import json

from langchain.chat_models import init_chat_model
from pymilvus import DataType

from kb_main.config.config import LLMConfig, MilvusConfig
from kb_main.config.prompt import (
    ITEM_NAME_SYSTEM_PROMPT,
    ITEM_NAME_USER_PROMPT_TEMPLATE,
)
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool import bgem3_client_tool
from kb_main.tool.logger import logger
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.milvus_client_tool import get_milvus_client
from kb_main.tool.bgem3_client_tool import get_bge_m3_embedding


class NodeItemNameRecognition(NodeBase):
    """
    主体识别节点：主体识别与标签提取
    """

    name = "node_item_name_recognition"

    def process(self, state: ImportGraphState):
        # 获取chunks及防御性校验
        chunks, file_title = self.get_chunks(state)

        #截取生成item_name的内容，由于llm的tokens限制
        chunks_str_k = self.get_chunks_content_k(chunks, file_title)

        #llm生成item_name
        item_name = self.get_item_name(chunks_str_k, file_title)

        #创建collection
        collection_name, milvus_client = self.create_collection()

        #写入item_name的向量化数据道milvus
        self.insert_data_2_milvus(chunks, collection_name, file_title, item_name, milvus_client)

        return {"item_name": item_name,
            "chunks": chunks}

    def insert_data_2_milvus(self, chunks, collection_name, file_title, item_name, milvus_client):
        # 4、将数据向量化写入milvus
        # 向量化
        embedding = get_bge_m3_embedding([item_name])
        data = {
            "item_name": item_name,
            "file_title": file_title,
            "dense_vector": embedding.get("dense")[0],
            "sparse_vector": embedding.get("sparse")[0],
        }
        # 幂等
        # milvus_client.load_collection(collection_name=collection_name)
        safe_file_title = (
            file_title.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        )
        filter_str = f"file_title=='{safe_file_title}'"
        milvus_client.delete(collection_name=collection_name, filter=filter_str)
        # 插入数据并落盘
        milvus_client.insert(collection_name=collection_name, data=data)
        milvus_client.flush(collection_name=collection_name)
        for chunk in chunks:
            chunk["item_name"] = item_name

    def create_collection(self):
        # 3创建collection
        milvus_client = get_milvus_client()
        collection_name = MilvusConfig.item_name_collection
        if not milvus_client.has_collection(collection_name):
            schema = milvus_client.create_schema(auto_id=True)
            schema.add_field(
                field_name="id", datatype=DataType.INT64, is_primary=True
            ).add_field(
                field_name="item_name", datatype=DataType.VARCHAR, max_length=100
            ).add_field(
                field_name="file_title", datatype=DataType.VARCHAR, max_length=100
            ).add_field(
                field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=1024
            ).add_field(
                field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR
            )

            index_params = milvus_client.prepare_index_params()
            index_params.add_index(
                field_name="dense_vector",
                index_type="IVF_FLAT",
                metric_type="COSINE",
                params={"nlist": 128, "nprobe": 10},
            )
            index_params.add_index(
                field_name="sparse_vector",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={
                    "inverted_index_algo": "DAAT_MAXSCORE", # 高效的稀疏检索算法
                },
            )
            milvus_client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )
        return collection_name, milvus_client

    def get_item_name(self, chunks_str_k, file_title):
        llm = init_chat_model(
            model=LLMConfig.item_model,
            model_provider="openai",
            api_key=LLMConfig.openai_api_key,
            base_url=LLMConfig.openai_api_base,
            temperature=LLMConfig.llm_default_temperature,
        )
        messages = [
            {"role": "system", "content": ITEM_NAME_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ITEM_NAME_USER_PROMPT_TEMPLATE.format(
                    file_title=file_title, context=chunks_str_k
                ),
            },
        ]
        res = llm.invoke(messages)
        item_name = res.content
        item_name = item_name.replace(" ", "").replace("\n", "").replace("\t", "")
        if not item_name:
            item_name = file_title
        return item_name

    def get_chunks_content_k(self, chunks, file_title):
        # 2拿到文档内容交给大模型生成产品名
        chunks_k = 20
        chunks_list_k = chunks[:chunks_k]
        chunks_str_k = ""
        llm_max_token = 10000
        for idx, chunk in enumerate(chunks_list_k):
            title = chunk.get("title")
            content = chunk.get("content")
            content_k = f"切片{idx}--{file_title}--{title}--{content}"
            chunks_str_k += content_k
            if len(chunks_str_k) > llm_max_token:
                chunks_str_k = chunks_str_k[:llm_max_token]
                break
        return chunks_str_k

    def get_chunks(self, state):
        # 1防御性校验
        chunks = state.get("chunks")
        if not chunks:
            logger.error("切片列表为空，不能进行产品名识别")
            raise Exception("切片列表为空，不能进行产品名识别")
        file_title = state.get("file_title")
        if not file_title:
            logger.error("file_title为空，不能进行产品名识别")
            raise Exception("file_title为空，不能进行产品名识别")
        return chunks, file_title


if __name__ == "__main__":
    node = NodeItemNameRecognition()

    with open(
        r"D:\data\output\hak180产品安全手册\hak180产品安全手册_new_backup.json",
        "r",
        encoding="utf-8",
    ) as f:
        chunks = json.load(f)
    state = {"chunks": chunks, "file_title": "hak180产品安全手册"}
    res = node(state)
    logger.info(json_format(res))
