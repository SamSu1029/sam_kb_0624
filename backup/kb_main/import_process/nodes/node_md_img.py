from ast import main
import base64
import os
from pyexpat import errors
import re
import time
from collections import deque
from pathlib import Path

from langchain.chat_models import init_chat_model
from minio.deleteobjects import DeleteObject


from kb_main.config.config import LLMConfig, MinIoConfig
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.json_format_tool import json_format
from kb_main.tool.logger import logger
from kb_main.tool.minio_client_tool import get_minio_client


class NodeMDImg(NodeBase):
    """
    MarkDown图片处理节点：多模态图片理解
    """

    name = "node_md_img"

    def process(self, state: ImportGraphState):
        # 1. 获取文件路径md_path对文件路径和文件进行非空校验，返回文件的路径Path对象（后续串联起来直接获取md_content）
        md_path = state.get("md_path", "")
        if not md_path:
            logger.error("md_path未提供")
            raise Exception("md_path未提供")
        md_path_obj = Path(md_path)
        if not md_path_obj.exists():
            logger.error("md路径不存在")
            raise Exception("md路径不存在")

        # 2. 根据文件md_path得到文件内容,判断md文件是否有内容
        with open(md_path_obj, "r", encoding="utf-8") as f:
            md_content = f.read()
        if not md_content:
            logger.error("md文件内容为空")
            raise Exception("md文件内容为空")

        # 3. 根据md_path的Path对象.parent / images组装文件夹的路径对象进行非空校验
        # 如果不存在，直接返回md_content
        images_dir_path_obj = md_path_obj.parent / "images"
        if not images_dir_path_obj.exists():
            logger.warning(f"图片目录不存在:{images_dir_path_obj}")
            return {"md_content": md_content}

        # 4.通过os.listdir(images的路径)得到图片名称的列表（可以打印测试，是带后缀的文件名，没有全路径）
        # 如果不存在，直接返回md_content
        images_dir_content_list = os.listdir(images_dir_path_obj)
        if not images_dir_content_list:
            logger.warning(f"图片目录为空:{images_dir_path_obj}")
            return {"md_content": md_content}

        # 5.遍历图片名称的列表
        IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
        MAX_CONTENT_LENGTH = 250
        images_with_content_list = []
        for image_name in images_dir_content_list:
            # 5-1：图片的后缀要在提前定义好的后缀列表当中，如果不在需要提示，continue
            if Path(image_name).suffix.lower() not in IMAGE_EXTENSIONS:
                logger.warning(f"图片扩展名不合法：{image_name}")
                continue
            # 5-2：定义正则从md_content当中匹配图片，非空校验，如果没找到就提示 continue
            # 先粗过滤
            if image_name not in md_content:
                logger.warning(f"图片不存在于md内容中：{image_name}")
                continue
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(image_name) + r"\)")
            match = pattern.search(md_content)
            if not match:
                logger.warning(f"图片在md内容未被正确引用：{image_name}")
                continue

            # 5-3：正则匹配成功，根据match.span(),获取图片的起始位置和结束位置
            start_index, end_index = match.span()

            # 5-4：切片找到图片的上文和下文
            pre_content = md_content[
                max(0, start_index - MAX_CONTENT_LENGTH) : start_index
            ]
            post_content = md_content[end_index : end_index + MAX_CONTENT_LENGTH]

            # 5-5：循环外部定义图片列表，把每个图片整理成字典：image_name  image_path(组装)  pre_text  post_text 追加到列表
            images_with_content_list.append(
                {
                    "image_name": image_name,
                    "image_path": str(images_dir_path_obj / image_name),
                    "pre_content": pre_content,
                    "post_content": post_content,
                }
            )

        # 6.模型生成摘要：
        # 6-1： 配置模型参数,模型厂商是阿里云百练,写在.env当中，全部做成配置类
        vlm = init_chat_model(
            model=LLMConfig.vl_model,
            model_provider="openai",
            api_key=LLMConfig.openai_api_key,
            base_url=LLMConfig.openai_api_base,
            temperature=LLMConfig.llm_default_temperature,
        )
        # 6-2：设计算法滑动门限定频率
        a62 = """
        准备双向队列 deque()
			队列当中保存的是请求的时间戳
				思想：
					队列当中保留的是1分钟内发送的请求，超过1分钟的请求要出队
					队列当中保留的请求最大是30个，可以自己设定
        """
        dq = deque(maxlen=30)
        images_with_summary_list = []
        # 循环遍历图片列表
        for images_with_context in images_with_content_list:
            current_time = time.time()  # 循环内定义当前时间
            # 1. 清理滑动窗口外的过期请求时间戳，保证队列仅存窗口内的请求
            while dq and current_time - dq[0] > 60:
                dq.popleft()
            # 2. 窗口内请求数达上限，计算并阻塞等待剩余时间,阻塞后清理过期时间,需要获取新的当前时间戳 current_time
            if len(dq) == dq.maxlen:
                wait_time = 60 - (current_time - dq[0])
                time.sleep(wait_time)
                current_time = time.time()
                while current_time - dq[0] > 60:
                    dq.popleft()
            # 3. 记录当前请求时间戳，加入滑动窗口队列
            dq.append(current_time)
            # 4. base64编码处理图片，使用LLM和提示词生成图片摘要,调用模型传递的用户消息，可以参考qwen3-vl-flash模型的api
            with open(images_with_context.get("image_path"), "rb") as f:
                image_data = f.read()
                image_data_base64 = base64.b64encode(image_data).decode("utf-8")
            # 5. 循环外部定义图片列表，调大模型，根据提示词生成摘要summary，把每个图片整理成字典：image_name  image_path(组装)  summary 追加到列表
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式是base64格式规定的
                                "url": f"data:image/jpeg;base64,{image_data_base64}"
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""这是一张图片，图片上文部分为"{images_with_context.get("pre_content")}"，
                                                    下文部分为"{images_with_context.get("post_content")}"，
                                                    请用中文简要总结这张图片的摘要,字数在50字以内。""",
                        },
                    ],
                },
            ]
            res = vlm.invoke(messages)
            images_with_summary_list.append(
                {
                    "image_name": images_with_context.get("image_name"),
                    "image_path": images_with_context.get("image_path"),
                    "summary": res.content,
                }
            )

        # 生成图片线上url（替换内容当中的图片摘要和url）
        # 1.上传图片到minio，替换原文的图片地址为minio的地址
        minio_client = get_minio_client()
        bucket_name = MinIoConfig.minio_bucket_name
        upload_dir = MinIoConfig.minio_img_dir
        # 幂等性清理旧数据（去除冗余数据，别出现相同的图片）参考官网github案例
        delete_object_list = map(
            lambda x: DeleteObject(x.object_name),
            minio_client.list_objects(
                bucket_name=bucket_name,
                prefix=upload_dir,
                recursive=True,
            ),
        )
        errors = minio_client.remove_objects(
            bucket_name=bucket_name,
            delete_object_list=delete_object_list,
        )
        for error in errors:
            print("error occurred when deleting object", error)

        # 循环遍历上传图片fput_object，注意参数 object文件名不带桶的名字，只是上传目录 + 文件名字
        images_with_summary_and_url_list=[]
        for images_with_summary in images_with_summary_list:
            result = minio_client.fput_object(
                bucket_name=bucket_name,
                object_name=upload_dir + "/" + images_with_summary.get("image_name"),
                file_path=images_with_summary.get("image_path"),
            )
            images_with_summary_and_url_list.append({
                **images_with_summary,
                "image_url": f"http://{MinIoConfig.minio_endpoint}/{bucket_name}/{upload_dir}/{images_with_summary.get('image_name')}"
            })

        # 2.循环遍历图片列表，替换md_content当中的图片地址为minio的地址
        for images_with_summary_and_url in images_with_summary_and_url_list:
            # 替换md内容，即用图片摘要作为 [alt] 文本，用远程 URL 替代原来的本地路径 ![](images/677a08ee041965bbbdb6b483d6c17d5aaa36a26b6dc96870a2019f0307b8616f.jpg)
            pattern = re.compile(r"!\[.*?\]\(.*?" + re.escape(images_with_summary_and_url.get("image_name")) + r"\)")
            md_content=pattern.sub(
                lambda match: f"![{images_with_summary_and_url.get('summary')}]({images_with_summary_and_url.get('image_url')})",
                md_content
            )
        new_md_path_obj=md_path_obj.parent / f"{md_path_obj.stem}_new.md"
        with open(new_md_path_obj, "w", encoding="utf-8") as f:
            f.write(md_content) 

        return {"md_content": md_content, "md_path": str(new_md_path_obj)}


if __name__ == "__main__":
    node = NodeMDImg()
    state = {"md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册.md"}
    res = node(state)
    logger.info(res)
"""
输入：md_path    # MarkDown文件路径
"""
"""
delete_object_list = map(
    lambda x: DeleteObject(x.object_name),
    client.list_objects(
        bucket_name="my-bucket",
        prefix="my/prefix/",
        recursive=True,
    ),
)
errors = client.remove_objects(
    bucket_name="my-bucket",
    delete_object_list=delete_object_list,
)
for error in errors:
    print("error occurred when deleting object", error)
"""

"""
# Upload data.
result = client.fput_object(
    bucket_name="my-bucket",
    object_name="my-object",
    file_path="my-filename",
)
"""
