
import json

from pymilvus import DataType

from kb_main.config.config import MilvusConfig
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
from kb_main.tool.milvus_client_tool import get_milvus_client


class NodeImportMilvus(NodeBase):
    """
    导入向量库节点：数据持久化
    """
    name = "node_import_milvus"

    def get_chunks(self, state):
        chunks = state.get("chunks", "")
        if not chunks:
            logger.error("导入向量库节点：数据持久化，未找到chunks")
            raise Exception("导入向量库节点：数据持久化，未找到chunks")
        dim = len(chunks[0].get("dense_vector"))
        file_title = chunks[0].get("file_title")
        return chunks, dim, file_title

    def create_milvus_collection(self, dim):
        milvus_client = get_milvus_client()
        collection_name = MilvusConfig.chunks_collection
        if not milvus_client:
            logger.error("milvus_client初始化失败")
            raise Exception("milvus_client初始化失败")
        if not milvus_client.has_collection(collection_name):
            schema = milvus_client.create_schema(
                auto_id=True,
            )

            schema.add_field(
                field_name="id",
                datatype=DataType.INT64,
                is_primary=True,
            ).add_field(
                field_name="file_title",
                datatype=DataType.VARCHAR,
                max_length=100,
            ).add_field(
                field_name="title",
                datatype=DataType.VARCHAR,
                max_length=100,
            ).add_field(
                field_name="content",
                datatype=DataType.VARCHAR,
                max_length=5000,
            ).add_field(
                field_name="item_name",
                datatype=DataType.VARCHAR,
                max_length=100,
            ).add_field(
                field_name="part",
                datatype=DataType.INT64,
            ).add_field(
                field_name="dense_vector",
                datatype=DataType.FLOAT_VECTOR,
                dim=dim,
            ).add_field(
                field_name="sparse_vector",
                datatype=DataType.SPARSE_FLOAT_VECTOR,
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
                    "inverted_index_algo": "DAAT_MAXSCORE",
                    # 高效的稀疏检索算法
                }
            )

            milvus_client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params,
            )
        return collection_name, milvus_client

    def insert_data(self, chunks, collection_name, file_title, milvus_client):
        # 幂等删除file_title重复的记录,删除数据记得先加载表
        milvus_client.load_collection(collection_name=collection_name)
        file_title = file_title.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
        filter_str = f"file_title == '{file_title}'"
        milvus_client.delete(collection_name=collection_name, filter=filter_str)
        # 插入数据
        res = milvus_client.insert(
            collection_name=collection_name,
            data=chunks,
        )
        logger.info(res)
        # 把插入数据返回的id，回填到对应的chunks,其实没什么用就是为了保证数据的完整性
        ids = res.get("ids")
        if ids:
            for i, chunk in enumerate(chunks):
                chunk["id"] = ids[i]

    def process(self, state: ImportGraphState):
        # 第一大步：获取上一步向量化后的chunks
        chunks, dim, file_title = self.get_chunks(state)

        # 第二大步：创建milvus的collection
        collection_name, milvus_client = self.create_milvus_collection(dim)

        # 第三大步：幂等性删除并插入数据到milvus中
        self.insert_data(chunks, collection_name, file_title, milvus_client)

        

        return {
            "chunks": chunks,
        }




if __name__ == '__main__':
    node = NodeImportMilvus()
    with open(r"D:\data\output\hak180产品安全手册\embedding_chunks.json","r",encoding="utf-8") as f:
        chunks = json.load(f)
    init_state = {
        "chunks": chunks
    }
    result = node(init_state)
    logger.info(json_format(result))


