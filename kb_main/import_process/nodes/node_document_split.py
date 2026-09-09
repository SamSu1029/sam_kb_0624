from langchain_text_splitters import RecursiveCharacterTextSplitter

from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.logger import logger
from kb_main.tool.json_format_tool import json_format
from pathlib import Path
import re


class NodeDocumentSplit(NodeBase):
    """
    文档切分节点：智能文档切片
    """

    name = "node_document_split"

    def get_md_content(self,state):
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("md_path路径未提供")
            raise ValueError("md_path路径未提供")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("md_path路径不存在")
            raise ValueError("md_path路径不存在")
        file_title = state.get("file_title", "")
        if not file_title:
            file_title = md_path_obj.stem
        
        # 读取行一个node处理的md_content
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        if not md_content:
            logger.error("md文件内容为空")
            raise ValueError("md文件内容为空")
        
        md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
        return md_content,file_title,md_path_obj

    def get_section_list(self,md_content,file_title):
        md_line_list = md_content.split("\n")
        
        # 按照标题合并，需要遍历列表找标题，这里需要明确标题是#开头的，而且要排除代码块中的#
        # 所以第一步需要判断是否是代码块当中的#，如果不是才能进行下一步操作
        # 代码块是以~~~或```开头和结尾的，需要正则判断，而且还要看开头和结尾是否一致
        code_pattern = r"^(`{3,}|~{3,})"  # 代码块正则
        title_pattern = r"^\s*#{1,6}\s+.+"  # 标题正则
        is_in_block = False  # 是否在代码块内标识
        marker = None  # 代码块开头标识 ~~~或```
        
        section_list = []
        current_index = 0
        
        for idx, line in enumerate(md_line_list):
            line = line.strip()
            # 判断是否匹配代码块
            code_match = re.match(code_pattern, line)
            if code_match:
                # 能匹配到还分两种情况，是开头，是结尾，判断下
                if not is_in_block:  # 是开头
                    marker = code_match.group(1)  # 匹配的字符
                    is_in_block = True
                    logger.info(f"代码块开始{marker}")
                else:  # 是结尾，还要看结尾是否与开头匹配
                    if marker == code_match.group(1):
                        logger.info(f"代码块结束{marker}")
                        is_in_block = False
                        marker = None
        
            # 不在代码块中,判断是不是标题，如果是就处理，不是就不用处理
            # 如何处理呢，这一步的目的是获取同一个标题的内容，连同标题和文件title一起组装成字典存起来
            title_match = re.match(title_pattern, line)
            if not is_in_block and title_match:
                # 核心方法是定义一个标题的初始下标0，然后每次出现标题后，将上一个标题下标到本次之前的内容从md_line_list取出来在拼接，然后更新初始下标
                split_title_list = md_line_list[current_index:idx]
                if split_title_list:
                    title_content = "\n".join(split_title_list)
                    section_dict = {
                        "title": split_title_list[0]
                        if title_content.startswith("#")
                        else "无标题",
                        "content": title_content,
                        "file_title": file_title
                    }
                    section_list.append(section_dict)
                current_index = idx
        
        
        section_list.append({
            "title": md_line_list[current_index],
            "content": '\n'.join(md_line_list[current_index:]),
            "file_title":file_title
            })
        return section_list

    def get_final_section_list(self,section_list,md_path_obj,file_title):
        max_length=300
        over_lap=30
        final_section_list=[]
        
        splitter=RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
            chunk_size=max_length,
            chunk_overlap=over_lap
        )
        
        for section in section_list:
            content=section.get("content")
            title=section.get("title")
            real_content=content[len(title):] if content.startswith('#') else content
        
            if (len(real_content)<max_length) or ('<table' in real_content):
                final_section_list.append({
                    **section,
                    "part":0
                })
        
            split_chunk_list=splitter.split_text(real_content)
            for index,chunk in enumerate(split_chunk_list,start=1):
                final_section_list.append({
                    "title":title,
                    "content":title + '\n\n'+chunk,
                    "file_title":file_title,
                    "part":index
        
                })
        with open(md_path_obj.parent / "chunks.json" ,'w',encoding='utf-8') as f:
            f.write(json_format(final_section_list))

        return final_section_list
    
    def process(self, state: ImportGraphState):
        #第一大步：获取md文件内容，文件标题及路径，并进行校验
        md_content,file_title,md_path_obj=self.get_md_content(state)

        #第二大步：对md内容进行切割，先按行切，在根据标题合并，返回列表
        section_list=self.get_section_list(md_content,file_title)

        # 第三大步：长切短合，返回{"chunks":final_section_list}
        final_section_list=self.get_final_section_list(section_list,md_path_obj,file_title)

        
        return {"chunks":final_section_list}


if __name__ == "__main__":
    node = NodeDocumentSplit()
    init_state = {
        "md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册_new.md",
        "file_title": "hak180产品安全手册",
    }
    result = node(init_state)
    logger.info(json_format(result))
