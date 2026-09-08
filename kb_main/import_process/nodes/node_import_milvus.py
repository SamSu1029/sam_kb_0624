from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState


class NodeImportMilvus(NodeBase):
    """
    导入向量库节点：数据持久化
    """

    name = "node_import_milvus"

    def process(self, state: ImportGraphState):


        return state