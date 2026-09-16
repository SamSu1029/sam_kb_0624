from pathlib import Path
import re

from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from langchain_text_splitters import RecursiveCharacterTextSplitter


# 输入 md_path file_title 输出chunks_list
class NodeDocumentSplit(NodeBase):
    """
    文档切分节点：智能文档切片
    接收:md_path,file_title
    输出:chunks_list，带有标题、内容、文件标题
    """

    name = "node_document_split"

    def process(self, state: ImportGraphState):
        #1、防御性校验，统一分隔符
        file_title, md_content, md_path_obj = self.process_md_content(state)
        #2、按行切分然后拼接，得到章节内容列表，最后同行标题和文件标题一并封装为字典，得到章节列表
        section_list = self.get_section_list(file_title, md_content)
        #3、将章节内容列表中的每个章节内容，用切分器切分，得到最终的chunks
        final_chunks_list = self.get_chunks_list(file_title, md_path_obj, section_list)

        return {"chunks": final_chunks_list}

    def get_chunks_list(self, file_title, md_path_obj, section_list):
        final_chunks_list = []
        max_chunk_size = 300
        # 文档切分，短章节及表格不做处理，超长章节要用切分器切分
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=30,
            # length_function=len,
            # 有图片内容，标识符不可以为图片标题中的符号
            separators=["\n\n", "\n", "。", "！", "？", "；", "!", "?", ";", " "]
        )
        # 遍历上一步生成的章节内容
        for section in section_list:
            # 要先拿到章节内容中不包含标题的内容
            section_content = section.get("content")
            title = section.get("title")
            if section_content.startswith('#'):
                first_newline = section_content.find('\n')
                real_content = section_content[first_newline + 1:] if first_newline != -1 else section_content
            else:
                real_content = section_content

            # 短内容及表格不做处理
            if len(real_content) < max_chunk_size or '<table' in real_content:
                final_chunks_list.append({
                    **section,
                    "part": 0
                })
            else:
                chunks = splitter.split_text(real_content)
                for idx, chunk in enumerate(chunks, start=1):
                    final_chunks_list.append({
                        "title": title,
                        "content": title + '\n\n' + chunk,
                        "file_title": file_title,
                        "part":idx
                    })
        # 备份一份到本地
        backup_path = md_path_obj.parent / f"{md_path_obj.stem}_backup.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(json_format(final_chunks_list))
            logger.info(f"备份文件已保存到 {backup_path}")
        return final_chunks_list

    def get_section_list(self, file_title, md_content):
        # 文档切分，先按行切分
        line_split_list = md_content.split("\n")
        
        # 将同一标题行下的内容拼接到一起
        # 需要判断行是否在代码块内，以及是否是标题行
        # 构造代码块正则及标题行正则
        code_pattern = r"^(`{3,}|~{3,})"  # 代码块正则
        title_pattern = r"^\s*#{1,6}\s+.+"  # 标题正则
        # 需要判断行是否在代码块内，以及代码块开始标识（~|`）
        in_code_block = False
        marker = None
        # 需要记录当前标题行在line_split_list中的索引
        current_index = 0
        section_list = []  # 存储章节内容
        # 遍历行切分后的内容列表
        for idx, line in enumerate(line_split_list):
            line = line.strip()
            code_match = re.match(code_pattern, line)
            title_match = re.match(title_pattern, line)

            # 是否是代码块开始或结束行
            if code_match:
                # 如果是，判断行是否在代码块内
                if in_code_block:
                    # 如果是，判断是否和代码块开始标识一致
                    if marker == code_match.group(1):
                        # 一致，是结束行，并且重置代码块标识
                        logger.info(f"该行是代码块结束，标识{marker}")
                        marker = None
                        in_code_block = False
                # 如果不在代码块内，是开始行，并且设置代码块标识
                else:
                    logger.info(f"该行是代码块开始，标识{code_match.group(1)}")
                    marker = code_match.group(1)
                    in_code_block = True

            # 是否是标题行
            if not in_code_block and title_match:
                # 是标题行，将上一个标题行下的内容拼接在一起
                tmp_list = line_split_list[current_index:idx]
                if tmp_list:
                    section_content = "\n".join(tmp_list)
                    section_list.append({
                        "title": tmp_list[0] if section_content.startswith("#") else "无标题",
                        "content": section_content,
                        "file_title": file_title
                    })
                current_index = idx
        # 最后一个标题内容
        tmp_list = line_split_list[current_index:]
        if tmp_list:
            section_content = "\n".join(tmp_list)
            section_list.append({
                "title": tmp_list[0] if section_content.startswith("#") else "无标题",
                "content": section_content,
                "file_title": file_title
            })
        return section_list

    def process_md_content(self, state):
        # 防御性检查
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
            logger.info(f"没有file_title，传入md文件名: {md_path_obj.stem}")
        # 读取文件内容
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        # 检查文件内容是否为空
        if not md_content:
            logger.error("文件内容为空")
            raise Exception("文件内容为空")
        # 统一换行符
        md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
        return file_title, md_content, md_path_obj


if __name__ == "__main__":
    node = NodeDocumentSplit()
    init_state = {
        "md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册_new.md",
        "file_title": "hak180产品安全手册",
    }
    result = node(init_state)
    logger.info(json_format(result))
