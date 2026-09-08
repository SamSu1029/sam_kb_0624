from pathlib import Path

from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger


class NodeEntry(NodeBase):
    """
    入口节点：任务分发
    """

    name = "node_entry"

    def process(self, state: ImportGraphState):
        # 新进行防御性编程
        local_file_path=state.get("local_file_path",'')
        # 判断state中是否提供'local_file_path'属性
        if not local_file_path:
            logger.error("local_file_path路径必须提供") #也就是state中要有
            raise ValueError("local_file_path路径必须提供")

        local_file_path_obj=Path(local_file_path)
        # 判断文件是否存在
        if not local_file_path_obj.exists():
            logger.error("local_file_path文件不存在")
            raise ValueError("local_file_path文件不存在")

        logger.info("local_file_path开始进行入口判断")

        # 下边判断文件类型，对state进行赋值，后期根据这些值配置路由
        file_title = local_file_path_obj.stem  # 文件标题（文件名去后缀）Path对象的方法
        suffix = local_file_path_obj.suffix  # 文件后缀
        if suffix.lower()==".md":
            return {
                "file_title": file_title,
                "is_md_read_enabled": True,
                "md_path": local_file_path
            }
        elif suffix.lower()==".pdf":
            return {
                "file_title": file_title,
                "is_pdf_read_enabled": True,
                "pdf_path": local_file_path
            }
        else:
            logger.error("不支持的文件类型")
            raise ValueError(f"不支持的文件类型：{suffix}")



if __name__ == '__main__':
    node = NodeEntry()
    init_state = {
        "local_file_path": r"D:\data\output\hak180产品安全手册.pdf"
    }
    result = node(init_state)
    logger.info(json_format(result))

"""
输入：local_file_path
输出：file_title, is_md_read_enabled, md_path, is_pdf_read_enabled, pdf_path

1、首先进行防御性编程，判断state中是否提供'local_file_path'属性
2、判断文件是否存在
3、判断文件类型，对state进行赋值，后期根据这些值配置路由

我在想state中关于pdf和md的属性有点冗余
可以加一个属性来判断文件类型，比如"file_type"
后边就不用再分pdf_path和md_path了
"""
"""
.exists() 方法用于判断文件是否存在。
.suffix 方法用于获取文件的后缀名。
.stem 方法用于获取文件名（不包括后缀名）。


| 方法 | 含义 |
| --- | --- |
| path.exists() | 路径本身是否存在 |
| path.is_dir() | 路径是否是一个目录 |
| path.is_file() | 路径是否是一个文件 |
| any(path.iterdir()) | 目录下是否有内容 |

"""
