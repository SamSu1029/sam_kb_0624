import shutil
import time
import zipfile

from kb_main.config.config import MineruConfig
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
from pathlib import Path
import requests

# 确定要用那些state属性 输入：pdf_path,local_dir。输出：md_content,md_path
class NodePDFToMD(NodeBase):
    """
    PDF 转 Markdown 节点：PDF结构化解析
    """

    name = "node_pdf_to_md"


    def check_input(self,state):
        pdf_path = state.get("pdf_path", "")  # PDF 文件路径 (如果输入是PDF)
        if not pdf_path:
            logger.error("pdf_path路径必须提供")
            raise ValueError("pdf_path路径必须提供")

        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error("pdf_path文件不存在")
            raise ValueError("pdf_path文件不存在")

        local_dir = state.get("local_dir", "")  # 当前工作目录或输出目录
        if not local_dir:
            logger.error("local_dir路径必须提供")
            raise ValueError("local_dir路径必须提供")
        local_dir_obj = Path(local_dir)
        if not local_dir_obj.exists():
            local_dir_obj.mkdir(parents=True, exist_ok=True)
            logger.info(f"local_dir文件夹不存在，已创建：{local_dir}")

        return pdf_path,pdf_path_obj,local_dir_obj

    def upload_pdf_to_mineru(self, pdf_path, pdf_path_obj):
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

        response = requests.post(url, headers=header, json=data,timeout=30)
        # 请求是否成功
        if response.status_code != 200:
            logger.error("上传pdf文件请求失败")
            raise Exception("上传pdf文件请求失败")
        logger.info("上传pdf文件请求成功")
        result = response.json()

        # 请求数据是否成功
        if result["code"] != 0:
            logger.error("上传pdf文件请求数据失败")
            raise Exception("上传pdf文件请求数据失败")
        logger.info("上传pdf文件请求数据成功")
        batch_id = result["data"]["batch_id"]
        urls = result["data"]["file_urls"]

        for i in range(0, len(urls)):
            with open(file_path[i], 'rb') as f:
                res_upload = requests.put(urls[i], data=f,timeout=60)
                if res_upload.status_code == 200:
                    logger.info(f"{urls[i]} 上传成功")
                else:
                    logger.error(f"{urls[i]} 上传失败")
                    raise Exception(f"{urls[i]} 上传失败")
        return batch_id

    def get_zip_url(self, batch_id):
        token = MineruConfig.mineru_token
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        max_time = 300
        used_time = 0
        while True:
            start_time = time.time()
            try:
                res = requests.get(url, headers=header,timeout=30)
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
                return full_zip_url
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

    def download_zip_file(self, full_zip_url,pdf_path_obj,local_dir_obj):
        md_zip_res = requests.get(full_zip_url,timeout=60)
        if md_zip_res.status_code != 200:
            logger.error("zip文件下载请求失败")
            raise Exception("zip文件下载请求失败")
        md_zip_content = md_zip_res.content

        md_zip_path_obj = local_dir_obj / f"{pdf_path_obj.stem}.zip"

        with open(md_zip_path_obj, 'wb') as f:
            f.write(md_zip_content)
        return md_zip_path_obj

    def unzip_file(self,local_dir_obj ,pdf_path_obj,md_zip_path_obj):
        unzip_file_path_obj=local_dir_obj / pdf_path_obj.stem
        # 判断解压文件夹是否存在，存在则删除并创建
        if unzip_file_path_obj.exists():
            shutil.rmtree(unzip_file_path_obj)
        unzip_file_path_obj.mkdir(parents=True, exist_ok=True)
        # 解压
        with zipfile.ZipFile(md_zip_path_obj, 'r') as zf:
            zf.extractall(unzip_file_path_obj)
        return unzip_file_path_obj
    def rename_and_read_file(self,unzip_file_path_obj,pdf_path_obj):
        origin_md_path_obj = unzip_file_path_obj / "full.md"
        new_md_path_obj = origin_md_path_obj.with_name(f"{pdf_path_obj.stem}.md") #传文件名返回整个文件路径对象
        origin_md_path_obj.rename(new_md_path_obj)

        with open(new_md_path_obj, 'r', encoding='utf-8') as f:
            md_content = f.read()
        return md_content,new_md_path_obj

    def process(self, state: ImportGraphState):
        # 校验输入内容属性集地址是否存在
        pdf_path, pdf_path_obj, local_dir_obj = self.check_input(state)

        # 上传pdf文件到mineru获取batch_id
        batch_id = self.upload_pdf_to_mineru(pdf_path, pdf_path_obj)

        # 等待mineru处理完成，我们需要轮询给mineru发请求，获取压缩包的下载地址
        full_zip_url = self.get_zip_url(batch_id)

        # 下载zip文件
        md_zip_path_obj=self.download_zip_file(full_zip_url,pdf_path_obj,local_dir_obj)

        # 解压
        unzip_file_path_obj=self.unzip_file(local_dir_obj,pdf_path_obj,md_zip_path_obj)

        # 解压完成后，原本的md文件叫 full.md,我们需要重命名
        # 读取md文件内容
        md_content,new_md_path_obj=self.rename_and_read_file(unzip_file_path_obj,pdf_path_obj)


        return {"md_content": md_content,
                "md_path": str(new_md_path_obj)}

if __name__ == '__main__':
    node = NodePDFToMD()
    init_state = {
        "pdf_path": r"D:\data\output\hak180产品安全手册.pdf",
        "local_dir": r"D:\data\output"
    }
    result = node(init_state)
    logger.info(json_format(result))

"""
输入： pdf_path,local_dir
输出： md_content,md_path
1、所有 requests 调用都要设置 timeout
如果 MinerU 服务无响应，requests.get/post 会无限挂起，max_time 超时机制完全失效

2、复用连接池，减少 TCP 握手开销  这块我还没搞清楚
def __init__(self):
        super().__init__()
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {MineruConfig.mineru_token}"
        })
        
3、upload_pdf_to_mineru中，这两步缺一不可：
POST 只是告诉 MinerU "我要传文件"，拿到预签名上传地址
PUT 才是把文件实际传上去
去掉 PUT 循环，MinerU 那边根本收不到你的 PDF，后续轮询必定超时。

"""