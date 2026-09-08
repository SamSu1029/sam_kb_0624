from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState


class NodeDocumentSplit(NodeBase):
    """
    文档切分节点：智能文档切片
    """

    name = "node_document_split"

    def process(self, state: ImportGraphState):


        return state