
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

        # 1、防御性校验
        pdf_path = state.get("pdf_path", "")
        if not pdf_path:
            logger.error("未上传pdf_path")
            raise Exception("未上传pdf_path")
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            logger.error(f"pdf_path路径不存在{pdf_path_obj}")
            raise Exception(f"pdf_path路径不存在{pdf_path_obj}")

        local_dir = state.get("local_dir", "")
        if not local_dir:
            logger.error("未上传local_dir")
            raise Exception("未上传local_dir")
        local_dir_obj = Path(local_dir)
        if not local_dir_obj.exists():
            local_dir_obj.mkdir(parents=True, exist_ok=True)
            logger.info(f"{local_dir_obj}路径不存在,已创建")

        # 2、上传pdf到mineru
        import requests

        token = MineruConfig.mineru_token
        url = "https://mineru.net/api/v4/file-urls/batch"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        data = {
            "files": [{"name": f"{pdf_path_obj.name}", "data_id": "abcd"}],
            "model_version": "vlm",
        }
        file_path = [pdf_path]

        response = requests.post(url, headers=header, json=data)
        if response.status_code != 200:
            logger.error(f"上传pdf网络请求失败：{response.status_code}")
            raise Exception(f"上传pdf网络请求失败：{response.status_code}")
        logger.info(f"上传pdf网络请求成功")
        upload_result = response.json()
        if upload_result["code"] != 0:
            logger.error(f"上传pdf业务请求失败：{upload_result.get('msg')}")
            raise Exception(f"上传pdf业务请求失败：{upload_result.get('msg')}")
        logger.info("上传pdf业务请求成功")
        batch_id = upload_result["data"]["batch_id"]
        urls = upload_result["data"]["file_urls"]

        for i in range(0, len(urls)):
            with open(file_path[i], "rb") as f:
                res_upload = requests.put(urls[i], data=f)
                if res_upload.status_code == 200:
                    logger.info(f"{urls[i]} 文件上传成功")
                else:
                    logger.error(f"{urls[i]} 文件上传失败")
                    raise Exception(f"{urls[i]} 文件上传失败")

        # 3、获取zip下载url
        token = MineruConfig.mineru_token
        batch_id = batch_id
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }

        # 轮询
        max_time = 300
        used_time = 0
        while True:
            start_time = time.time()
            try:
                download_url_response = requests.get(url, headers=header)
                if download_url_response.status_code != 200:
                    logger.error(
                        f"获取下载url网络请求失败：{download_url_response.status_code}"
                    )
                    raise Exception(
                        f"获取下载url网络请求失败：{download_url_response.status_code}"
                    )
                download_url_res = download_url_response.json()
                if download_url_res["code"] != 0:
                    logger.error(
                        f"获取下载url业务请求失败：{download_url_res.get('msg')}"
                    )
                    raise Exception(
                        f"获取下载url业务请求失败：{download_url_res.get('msg')}"
                    )
                data = download_url_res["data"]
                if data["extract_result"][0]["state"] != "done":
                    logger.info(
                        f"pdf转md处理中，状态：{data['extract_result'][0]['state']}"
                    )
                    end_time = time.time()
                    used_time += end_time - start_time
                    if used_time > max_time:
                        logger.error("获取下载url超时")
                        raise Exception("获取下载url超时")
                    time.sleep(2)
                    used_time += 2
                    continue

                full_zip_url = data["extract_result"][0]["full_zip_url"]
                logger.info(f"获取下载url成功:{full_zip_url}")
                break
            except Exception as e:
                logger.error(f"获取下载url失败:{e}")
                end_time = time.time()
                used_time += end_time - start_time
                if used_time > max_time:
                    logger.error("获取下载url超时")
                    raise Exception("获取下载url超时")
                time.sleep(2)
                used_time += 2
                continue

        # 4、下载zip文件
        download_zip_response = requests.get(full_zip_url)
        if download_zip_response.status_code != 200:
            logger.error(
                f"下载zip文件网络请求失败：{download_zip_response.status_code}"
            )
            raise Exception(
                f"下载zip文件网络请求失败：{download_zip_response.status_code}"
            )
        logger.info(f"下载zip文件网络请求成功")
        download_zip_content = download_zip_response.content

        download_zip_path_obj = local_dir_obj / f"{pdf_path_obj.stem}.zip"
        with open(download_zip_path_obj, "wb") as f:
            f.write(download_zip_content)
        logger.info(f"zip文件写入本地成功：{download_zip_path_obj}")

        # 5、解压zip文件
        unzip_path_obj = local_dir_obj / pdf_path_obj.stem
        if unzip_path_obj.exists():
            shutil.rmtree(unzip_path_obj)
            logger.info(f"解压目录存在，已删除:{unzip_path_obj}")
        unzip_path_obj.mkdir(parents=True, exist_ok=True)
        logger.info(f"解压目录创建成功:{unzip_path_obj}")

        with zipfile.ZipFile(download_zip_path_obj, "r") as z:
            z.extractall(unzip_path_obj)
        logger.info(f"zip文件解压成功")

        # 6、重命名
        origin_md_path_obj = unzip_path_obj / "full.md"
        new_md_path_obj = origin_md_path_obj.with_name(
            f"{pdf_path_obj.stem}.md"
        )  # 传文件名，返回整个path对象
        origin_md_path_obj.rename(new_md_path_obj)
        logger.info(f"md文件重命名成功:{new_md_path_obj}")

        with open(new_md_path_obj,'r',encoding='utf-8') as f:
            md_content=f.read()

        return {"md_path": str(new_md_path_obj),
                "md_content":md_content
                }



if __name__ == "__main__":
    node = NodePDFToMD()
    state = init_state = {
        "pdf_path": r"D:\data\output\hak180产品安全手册.pdf",
        "local_dir": r"D:\data\output",
    }
    res = node(state)
    logger.info(json_format(res))
