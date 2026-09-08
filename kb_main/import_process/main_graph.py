from langgraph.constants import END
from langgraph.graph import StateGraph
from kb_main.import_process.nodes.node_bge_embedding import NodeBGEEmbedding
from kb_main.import_process.nodes.node_document_split import NodeDocumentSplit
from kb_main.import_process.nodes.node_entry import NodeEntry
from kb_main.import_process.nodes.node_import_milvus import NodeImportMilvus
from kb_main.import_process.nodes.node_item_name_recognition import NodeItemNameRecognition
from kb_main.import_process.nodes.node_md_img import NodeMDImg
from kb_main.import_process.nodes.node_pdf_to_md import NodePDFToMD
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
# def after_entry_router(state:ImportGraphState):
#     is_md_read_enabled=state.get("is_md_read_enabled",False)
#     is_pdf_read_enabled=state.get("is_pdf_read_enabled",False)
#
#     if is_md_read_enabled:
#         return NodeMDImg.name
#     elif is_pdf_read_enabled:
#         return NodePDFToMD.name
#     else:
#         return END
#
# builder=StateGraph(state_schema=ImportGraphState)
#
# builder.add_node(NodeEntry.name,NodeEntry())
# builder.add_node(NodePDFToMD.name,NodePDFToMD())
# builder.add_node(NodeMDImg.name,NodeMDImg())
# builder.add_node(NodeDocumentSplit.name,NodeDocumentSplit())
# builder.add_node(NodeItemNameRecognition.name,NodeItemNameRecognition())
# builder.add_node(NodeBGEEmbedding.name,NodeBGEEmbedding())
# builder.add_node(NodeImportMilvus.name,NodeImportMilvus())
#
# builder.set_entry_point(NodeEntry.name)
# builder.add_conditional_edges(NodeEntry.name,after_entry_router)
# builder.add_edge(NodePDFToMD.name,NodeMDImg.name)
# builder.add_edge(NodeMDImg.name,NodeDocumentSplit.name)
# builder.add_edge(NodeDocumentSplit.name,NodeItemNameRecognition.name)
# builder.add_edge(NodeItemNameRecognition.name,NodeBGEEmbedding.name)
# builder.add_edge(NodeBGEEmbedding.name,NodeImportMilvus.name)
# builder.set_finish_point(NodeImportMilvus.name)
#
# graph=builder.compile()
# res=graph.invoke({"local_file_path": r"D:\data\output\hak180产品安全手册.pdf"})
# logger.info(res)



class MainGraphRunner:
    """
    知识库文档导入流程的总调度器（基于 LangGraph）

    整体流程：
        输入文件（PDF/MD）
            → NodeEntry          入口节点，判断文件类型，分发路由
            → NodePDFToMD        PDF 转 Markdown（仅 PDF 走这条路）
            → NodeMDImg          处理 Markdown 中的图片
            → NodeDocumentSplit  文档切片
            → NodeItemNameRecognition  识别每个片段的主题名称
            → NodeBGEEmbedding   生成向量嵌入
            → NodeImportMilvus   写入 Milvus 向量数据库

    职责分工：
        add_nodes()   - 注册所有处理节点到图（__init__ 时自动执行，只执行一次）
        add_edges()   - 定义节点之间的执行顺序和路由规则
        run()         - 懒加载编译图并启动执行（首次编译后缓存，复用不重复编译）
        create_and_run() - 工厂方法，一行完成"创建+执行"，对外暴露的简洁调用入口

    使用方式：
        MainGraphRunner.create_and_run({"local_file_path": "xxx.pdf"})
    """
    def __init__(self):
        # __init__ 是构造函数，创建对象时自动执行，用于一次性初始化工作
        # 执行顺序：创建 builder → 注册节点 → 注册边 → graph 置为 None 等待编译
        self.builder=StateGraph(state_schema=ImportGraphState)
        # 在 __init__ 中调用 add_nodes()：对象创建时自动注册所有节点，只执行一次
        # 如果不在 __init__ 里调，就需要在 run() 里手动调，会导致每次 run 都重复注册
        self.add_nodes()
        self.add_edges()
        # graph 先置为 None，后续在 run() 中懒加载（第一次用到时才编译）
        self.graph=None

    def add_nodes(self):
        self.builder.add_node(NodeEntry.name, NodeEntry())
        self.builder.add_node(NodePDFToMD.name, NodePDFToMD())
        self.builder.add_node(NodeMDImg.name, NodeMDImg())
        self.builder.add_node(NodeDocumentSplit.name, NodeDocumentSplit())
        self.builder.add_node(NodeItemNameRecognition.name, NodeItemNameRecognition())
        self.builder.add_node(NodeBGEEmbedding.name, NodeBGEEmbedding())
        self.builder.add_node(NodeImportMilvus.name, NodeImportMilvus())

    def add_edges(self):
        self.builder.set_entry_point(NodeEntry.name)
        self.builder.add_conditional_edges(NodeEntry.name, self.after_entry_router)
        self.builder.add_edge(NodePDFToMD.name, NodeMDImg.name)
        self.builder.add_edge(NodeMDImg.name, NodeDocumentSplit.name)
        self.builder.add_edge(NodeDocumentSplit.name, NodeItemNameRecognition.name)
        self.builder.add_edge(NodeItemNameRecognition.name, NodeBGEEmbedding.name)
        self.builder.add_edge(NodeBGEEmbedding.name, NodeImportMilvus.name)
        self.builder.set_finish_point(NodeImportMilvus.name)
    # @staticmethod
    # def after_entry_router(state: ImportGraphState):
    #     is_md_read_enabled = state.get("is_md_read_enabled", False)
    #     is_pdf_read_enabled = state.get("is_pdf_read_enabled", False)
    #
    #     if is_md_read_enabled:
    #         return NodeMDImg.name
    #     elif is_pdf_read_enabled:
    #         return NodePDFToMD.name
    #     else:
    #         return END

    def after_entry_router(self,state: ImportGraphState):
        is_md_read_enabled = state.get("is_md_read_enabled", False)
        is_pdf_read_enabled = state.get("is_pdf_read_enabled", False)

        if is_md_read_enabled:
            return NodeMDImg.name
        elif is_pdf_read_enabled:
            return NodePDFToMD.name
        else:
            return END
    def run(self,state):
        # 懒加载（Lazy Initialization）：第一次调用 run 时才编译图，编译完缓存到 self.graph
        # 后续再次调用 run 时直接复用，不重复编译，节省性能
        # 类比：compile() = 架锅（一次性准备），invoke() = 炒菜（可多次执行）
        if self.graph is None:
            self.graph=self.builder.compile()
        return self.graph.invoke(state)

    # @classmethod 类方法：cls 代表类本身，可以通过类名直接调用，不需要先创建对象
    # 工厂方法模式：把"创建对象 + 执行"封装成一步，调用方一行代码搞定
    # 使用方式：MainGraphRunner.create_and_run(state)
    # 好处：调用方不需要关心内部创建细节，语义清晰，以后扩展参数也只改这里
    @classmethod
    def create_and_run(cls,state):
        runner=cls()  # cls() 等价于 MainGraphRunner()，触发 __init__ 自动执行
        return runner.run(state)

if __name__ == '__main__':
    state = {"local_file_path": r"D:\data\output\hak180产品安全手册.pdf"}
    res=MainGraphRunner.create_and_run(state)
    logger.info(json_format(res))


"""
after_entry_router可以改为静态方法，因为她并没有用到类的任何属性
"""