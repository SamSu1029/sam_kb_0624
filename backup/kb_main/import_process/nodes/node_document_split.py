from pathlib import Path
import re

from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from langchain_text_splitters import RecursiveCharacterTextSplitter


class NodeDocumentSplit(NodeBase):
    """
    文档切分节点：智能文档切片
    接收:md_path,file_title
    """

    name = "node_document_split"

    def process(self, state: ImportGraphState):
        # 第一大步：将文件按行切分存到列表中
        # 校验接收值
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("md_path未上传")
            raise Exception("md_path未上传")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("md_path路径不存在")
            raise Exception("md_path路径不存在")
        file_title = state.get("file_title", "")
        if not file_title:
            file_title = md_path_obj.stem

        # 读取文件内容，注意这里已经是上一个node处理完的_new.md
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        if not md_content:
            logger.error("文件内容为空")
            raise Exception("文件内容为空")

        # 对文件内容做切分，由于不同操作系统的换行符不一致，要先处理成一致的
        md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
        md_line_list = md_content.split("\n")

        # 第二大步：粗分内容，目标是一个标题的内容放一起，同时带上标题内容和文件名标题存入字典中，再将每一个字典最终存入列表中
        # 按标题合并就要知道md文档的规则，标题是以# 开始的
        # 但是要排除掉在代码块中以# 开始的内容
        # 代码块是以```或者~~~开头和结尾的，而且必须前后一致
        # 创建正则
        code_pattern = r"^(`{3,}|~{3,})"  # 代码块正则
        title_pattern = r"^\s*#{1,6}\s+.+"  # 标题正则
        # 还要有两个标识，此次代码块开头是```还是~~~。改行是否在代码块内
        is_in_block = False  # 是否在代码块内标识
        marker = None  # 代码块开头标识 ~~~或```

        current_index = 0
        section_list = []
        # 遍历按行切分后的内容列表
        for idx, line in enumerate(md_line_list):
            line = line.strip()
            # 判断是否匹配代码块的正则
            code_match = re.match(code_pattern, line)
            if code_match:  # 匹配的上，还要通过在不在代码块中判断是开头还是结尾
                if not is_in_block:
                    # 是开头,更新这俩变量
                    marker = code_match.group(1)
                    is_in_block = True
                    logger.info(f"该行是代码块开始，标识{marker}")
                else:
                    # 是结尾，此时还要判断开头结尾标识是否一致
                    if marker == code_match.group(1):
                        logger.info(f"该行是代码块结束，标识{marker}")
                        marker = None
                        is_in_block = False

            # 真正判断该行是不是标题
            title_match = re.match(title_pattern, line)
            if not is_in_block and title_match:
                # 需要在循环外定义一个下标，代表每次标题行在列表中的index，然后每次有标题行出现就更新
                split_title_list = md_line_list[current_index:idx]
                if split_title_list:
                    title_content = "\n".join(split_title_list)
                    section_dict = {
                        "title": split_title_list[0]
                        if title_content.startswith("#")
                        else "无标题",
                        "content": title_content,
                        "file_title": file_title,
                    }
                    section_list.append(section_dict)
                current_index = idx

        section_list.append(
            {
                "title": md_line_list[current_index],
                "content": "\n".join(md_line_list[current_index:]),
                "file_title": file_title,
            }
        )

        # 第三大步：长切短合,结果存入新列表，这次的字典中要添加新属性part，主要是用来做切分后的下标记录
        # 构造切分器
        max_length = 300
        over_lap = 30
        splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
            chunk_size=max_length,
            chunk_overlap=over_lap,
        )

        # 遍历列表，判断切分
        final_section_list = []
        for section in section_list:
            # 首先要获取到真正的内容，现在的内容包含了标题
            content = section.get("content")
            title = section.get("title")
            real_content = content[len(title) :] if content.startswith("#") else content

            # 未超长以及表格不做切分
            if (len(real_content) < max_length) or "<table" in real_content:
                final_section_list.append({**section, "part": 0})
            # 超长的用切分器做切分
            split_chunk_list = splitter.split_text(real_content)
            for index, chunk in enumerate(split_chunk_list, start=1):
                final_section_list.append(
                    {
                        "title": title,
                        "file_title": file_title,
                        "content": title + "\n\n" + chunk,
                        "part":index
                    }
                )
        with open(md_path_obj.parent / "chunks.json",'w',encoding='utf-8') as f:
            f.write(json_format(final_section_list))

        return {"chunks":final_section_list}


if __name__ == "__main__":
    node = NodeDocumentSplit()
    init_state = {
        "md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册_new.md",
        "file_title": "hak180产品安全手册",
    }
    result = node(init_state)
    logger.info(json_format(result))
