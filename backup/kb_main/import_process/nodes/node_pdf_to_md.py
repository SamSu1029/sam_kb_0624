import shutil
import time
import zipfile
from pathlib import Path

from kb_main.config.config import MineruConfig
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger


# 确定要用那些state属性 输入：pdf_path,local_dir。输出：md_content,md_path
class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """

    name = "node_pdf_to_md"

    def process(self, state: ImportGraphState):

        # 1 防御性编程，输入属性是否存在
        pdf_path = state.get("pdf_path", "")
        if not pdf_path:
            logger.error("pdf_path路径未提供")
            raise ValueError("pdf_path路径未提供")

        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("pdf_path路径不存在")
            raise ValueError("pdf_path路径不存在")

        local_dir = state.get("local_dir", "")
        if not local_dir:
            logger.error("local_dir路径未提供")
            raise ValueError("local_dir路径未提供")
        local_dir_obj = Path(local_dir)
        if not local_dir_obj.exists():
            local_dir_obj.mkdir(parents=True, exist_ok=True)
            logger.info("local_dir路径不存在，已创建")

        # 2 上传pdf文件到mineru，拿到batch_id
        import requests

        token = MineruConfig.mineru_token
        url = "https://mineru.net/api/v4/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "files": [
                {"name": f"{pdf_path_obj.name}", "data_id": "abcd"}
            ],
            "model_version": "vlm"
        }
        file_path = [pdf_path]

        response = requests.post(url, headers=header, json=data)
        if response.status_code != 200:
            logger.error("上传pdf文件请求失败")
            raise Exception("上传pdf文件请求失败")
        logger.info("上传pdf文件请求成功")
        result = response.json()
        if result["code"] != 0:
            logger.error("上传pdf文件请求数据失败")
            raise Exception("上传pdf文件请求数据失败")
        logger.info("上传pdf文件请求数据成功")
        batch_id = result["data"]["batch_id"]
        urls = result["data"]["file_urls"]

        for i in range(0, len(urls)):
            with open(file_path[i], 'rb') as f:
                res_upload = requests.put(urls[i], data=f)
                if res_upload.status_code == 200:
                    logger.info(f"{urls[i]} 上传成功")
                else:
                    logger.error(f"{urls[i]} 上传失败")

        # 3、从mineru获取zip文件的下载地址
        token = MineruConfig.mineru_token
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        max_time = 300
        used_time = 0
        while True:
            start_time = time.time()
            res = requests.get(url, headers=header)
            try:
                if res.status_code != 200:
                    logger.error("获取zip文件下载地址请求失败")
                    raise Exception("获取zip文件下载地址请求失败")
                logger.info("获取zip文件下载地址请求成功")
                result = res.json()
                if result["code"] != 0:
                    logger.error("获取zip文件下载地址请求数据失败")
                    raise Exception("获取zip文件下载地址请求数据失败")
                logger.info("获取zip文件下载地址请求数据成功")

                if result["data"]["extract_result"][0]["state"] != "done":
                    logger.info("文件处理中,请稍候...")
                    end_time = time.time()
                    used_time += (end_time - start_time)
                    if used_time > max_time:
                        logger.error("文件处理超时")
                        raise Exception("文件处理超时")
                    time.sleep(3)
                    used_time += 3
                    continue
                full_zip_url = result["data"]["extract_result"][0]["full_zip_url"]
                logger.info(f"zip文件下载地址获取成功：{full_zip_url}")
                break
            except Exception as e:
                logger.error(f"获取处理结果请求异常，正在重试：{e}")
                end_time = time.time()
                used_time += (end_time - start_time)
                if used_time > max_time:
                    logger.error("获取zip文件下载地址超时")
                    raise Exception("获取zip文件下载地址超时")
                time.sleep(3)
                used_time += 3
                continue

        # 4、下载文件到本地
        response=requests.get(full_zip_url)
        if response.status_code!=200:
            logger.error("下载zip文件请求失败")
            raise Exception("下载zip文件请求失败")
        logger.info("下载zip文件请求成功")
        content=response.content
        md_zip_file_path_obj=local_dir_obj / f"{pdf_path_obj.stem}.zip"
        with open(md_zip_file_path_obj,'wb') as f:
            f.write(content)

#         解压文件
        #解压目录
        unzip_dir_path_obj = local_dir_obj/pdf_path_obj.stem
        if  unzip_dir_path_obj.exists():
            shutil.rmtree(unzip_dir_path_obj)
        unzip_dir_path_obj.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(md_zip_file_path_obj, 'r') as zf:
            zf.extractall(unzip_dir_path_obj)

        # 重命名
        origin_md_path_obj = unzip_dir_path_obj / "full.md"
        new_md_path_obj=origin_md_path_obj.with_name(f"{pdf_path_obj.stem}.md")
        origin_md_path_obj.rename(new_md_path_obj)

        with open(new_md_path_obj, 'r', encoding='utf-8') as f:
            md_content = f.read()

        return {"md_content": md_content, "md_path": str(new_md_path_obj)}





if __name__ == '__main__':
    node = NodePDFToMD()
    state = init_state = {
        "pdf_path": r"D:\data\output\hak180产品安全手册.pdf",
        "local_dir": r"D:\data\output"
    }
    res = node(state)
    logger.info(json_format(res))
