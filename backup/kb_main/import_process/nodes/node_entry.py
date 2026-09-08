from pathlib import Path

from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.logger import logger


class NodeEntry(NodeBase):
    """
    入口节点：任务分发
    """

    name = "node_entry"

    def process(self, state: ImportGraphState):
        local_file_path=state.get("local_file_path",'')
        if not local_file_path:
            logger.error("local_file_path没有上传")
            raise ValueError("local_file_path没有上传")
        local_file_path_obj = Path(local_file_path)
        if not local_file_path_obj.exists():
            logger.error("local_file_path文件不存在")
            raise ValueError("local_file_path文件不存在")

        file_title = local_file_path_obj.stem
        if local_file_path_obj.suffix.lower() == ".pdf":
            return {"pdf_path": local_file_path,
                    "file_title": file_title,
                    "is_pdf_read_enabled": True}
        elif local_file_path_obj.suffix.lower() == ".md":
            return {"md_path": local_file_path,
                    "file_title": file_title,
                    "is_md_read_enabled": True}
        else:
            logger.error("不支持的文件类型")
            raise ValueError("不支持的文件类型")




if __name__ == '__main__':
    node = NodeEntry()
    init_state = {
        "local_file_path": r"D:\data\output\hak180产品安全手册.pdf"
    }
    result = node(init_state)
    logger.info(result)

"""
1、首先进行防御性编程，判断state中是否提供'local_file_path'属性
2、判断文件是否存在
3、判断文件类型，对state进行赋值，后期根据这些值配置路由

我在想state中关于pdf和md的属性有点冗余
可以加一个属性来判断文件类型，比如"file_type"
后边就不用再分pdf_path和md_path了
"""
