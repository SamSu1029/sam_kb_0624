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

        # 文档切分，先按行切分
        line_split_list = md_content.split("\n")
        # ===== 错误写法（仅保留用于学习对照）：不能清除所有正文行的首尾空格 =====
        # line_split_list = [line.strip() for line in line_split_list]
        # ===== 修正逻辑：保留原始行，下面只用局部变量 line.strip() 辅助判断 =====

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
                    # ===== 修正逻辑：只规范化标题行，不改变正文中的缩进和行尾空格 =====
                    first_line = tmp_list[0]
                    normalized_title = first_line.strip()
                    has_title = bool(re.match(title_pattern, normalized_title))
                    section_list.append({
                        # 错误写法：标题前有空格时，startswith("#") 会错误地返回 False
                        # "title": tmp_list[0] if section_content.startswith("#") else "无标题",
                        "title": normalized_title if has_title else "无标题",
                        "content": section_content,
                        "file_title": file_title
                    })
                current_index = idx
        # 最后一个标题内容
        tmp_list = line_split_list[current_index:]
        if tmp_list:
            section_content = "\n".join(tmp_list)
            # ===== 修正逻辑：最后一个章节也只规范化标题行，正文保持原样 =====
            first_line = tmp_list[0]
            normalized_title = first_line.strip()
            has_title = bool(re.match(title_pattern, normalized_title))
            section_list.append({
                # 错误写法：标题前有空格时，startswith("#") 会错误地返回 False
                # "title": tmp_list[0] if section_content.startswith("#") else "无标题",
                "title": normalized_title if has_title else "无标题",
                "content": section_content,
                "file_title": file_title
            })
        final_chunks = []
        max_chunk_size = 300
        # 文档切分，短章节及表格不做处理，超长章节要用切分器切分
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chunk_size,
            chunk_overlap=30,
            length_function=len,
            # 有图片内容，标识符不可以为图片标题中的符号
            separators=["\n\n", "\n", "。", "！", "？", "；", "!", "?", ";", " "]
        )
        # 遍历上一步生成的章节内容
        for section in section_list:
            # 要先拿到章节内容中不包含标题的内容
            section_content = section.get("content")
            title = section.get("title")
            # ===== 错误写法（保留用于学习对照）：依赖正文必须直接以 # 开头 =====
            # if section_content.startswith('#'):
            #     first_newline = section_content.find('\n')
            #     real_content = section_content[first_newline + 1:] if first_newline != -1 else section_content
            # else:
            #     real_content = section_content
            # ===== 修正逻辑：根据上一步得到的标题字段判断，并正确处理只有标题的章节 =====
            if title != "无标题":
                _, separator, real_content = section_content.partition('\n')
                if not separator:
                    real_content = ""
            else:
                real_content = section_content

            # 短内容及表格不做处理
            if len(real_content) < max_chunk_size or '<table' in real_content:
                final_chunks.append({
                    **section,
                    "part": 0
                })
            else:
                chunks = splitter.split_text(real_content)
                for idx, chunk in enumerate(chunks, start=1):
                    final_chunks.append({
                        "title": title,
                        "content": title + '\n\n' + chunk,
                        "file_title": file_title,
                        "part":idx
                    })
        #备份一份到本地
        backup_path = md_path_obj.parent / f"{md_path_obj.stem}_backup.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            f.write(json_format(final_chunks))
            logger.info(f"备份文件已保存到 {backup_path}")

        return {"chunks": final_chunks}


if __name__ == "__main__":
    node = NodeDocumentSplit()
    init_state = {
        "md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册_new.md",
        "file_title": "hak180产品安全手册",
    }
    result = node(init_state)
    logger.info(json_format(result))
