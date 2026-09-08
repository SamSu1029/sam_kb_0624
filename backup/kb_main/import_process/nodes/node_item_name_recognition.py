from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState


class NodeItemNameRecognition(NodeBase):
    """
    主体识别节点：主体识别与标签提取
    """

    name = "node_item_name_recognition"

    def process(self, state: ImportGraphState):


        return state