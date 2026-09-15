import base64
import mimetypes
import os
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

    def check_and_get_md_content(self, state):
        """检查并获取MarkDown文件内容"""
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
        return md_content, md_path_obj

    def check_images_dir_and_content(self, md_content, md_path_obj):
        # 3. 根据md_path的Path对象.parent / images组装文件夹的路径对象进行非空校验
        # 如果不存在，直接返回md_content
        images_dir_path_obj = md_path_obj.parent / "images"
        if not images_dir_path_obj.exists():
            logger.warning(f"图片目录不存在:{images_dir_path_obj}")
            return None

        # 4.通过os.listdir(images的路径)得到图片名称的列表（可以打印测试，是带后缀的文件名，没有全路径）
        # 如果不存在，直接返回md_content
        images_dir_content_list = os.listdir(images_dir_path_obj)
        if not images_dir_content_list:
            logger.warning(f"图片目录为空:{images_dir_path_obj}")
            return None
        return images_dir_path_obj, images_dir_content_list

    def get_images_with_content_list(
        self, images_dir_content_list, images_dir_path_obj, md_content
    ):
        """获取图片携带上下文"""
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
        return images_with_content_list

    def get_images_with_summary_list(self, images_with_content_list):
        # 6.模型生成摘要：
        # 6-1： 配置模型参数,模型厂商是阿里云百练,写在.env当中，全部做成配置类
        vlm = init_chat_model(
            model=LLMConfig.vl_model,
            model_provider="openai",
            api_key=LLMConfig.openai_api_key,
            base_url=LLMConfig.openai_api_base,
            temperature=LLMConfig.llm_default_temperature,
            request_timeout=120,
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
                while dq and current_time - dq[0] > 60:
                    dq.popleft()
            # 3. 记录当前请求时间戳，加入滑动窗口队列
            dq.append(current_time)
            # 4. base64编码处理图片，使用LLM和提示词生成图片摘要,调用模型传递的用户消息，可以参考qwen3-vl-flash模型的api
            image_path = images_with_context.get("image_path")
            with open(image_path, "rb") as f:
                image_data = f.read()
            image_data_base64 = base64.b64encode(image_data).decode("utf-8")
            # 5. 循环外部定义图片列表，调大模型，根据提示词生成摘要summary，把每个图片整理成字典：image_name  image_path(组装)  summary 追加到列表
            # 根据图片实际后缀获取正确的MIME类型
            mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                # 这个格式是base64格式规定的
                                "url": f"data:{mime_type};base64,{image_data_base64}"
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
            try:
                res = vlm.invoke(messages)
                summary = res.content
            except Exception as e:
                logger.error(
                    f"图片摘要生成失败：{images_with_context.get('image_name')}，错误：{e}"
                )
                summary = "图片摘要生成失败"
            images_with_summary_list.append(
                {
                    "image_name": images_with_context.get("image_name"),
                    "image_path": image_path,
                    "summary": summary,
                }
            )
        return images_with_summary_list

    def get_image_with_summary_and_url_list(self, images_with_summary_list):
        # 上传图片到minio，自己构造图片的线上url，放到列表中
        minio_client = get_minio_client()
        bucket_name = MinIoConfig.minio_bucket_name
        upload_dir = MinIoConfig.minio_img_dir
        # 幂等性删除这个目录中的图片，防止重复上传
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

        # 构造添加url的字典写入列表
        images_with_summary_and_url_list = []
        for images_with_summary in images_with_summary_list:
            result = minio_client.fput_object(
                bucket_name=bucket_name,
                object_name=f"{upload_dir}/{images_with_summary.get('image_name')}",
                file_path=images_with_summary.get("image_path"),
                
            )
            images_with_summary_and_url_list.append(
                {
                    **images_with_summary,
                    "image_url": f"http://{MinIoConfig.minio_endpoint}/{bucket_name}/{upload_dir}/{images_with_summary.get('image_name')}",
                }
            )
        return images_with_summary_and_url_list

    def replace_md_images(
        self, md_content, md_path_obj, images_with_summary_and_url_list
    ):
        # 遍历图片列表
        for images_with_summary_and_url in images_with_summary_and_url_list:
            # 替换md内容，即用图片摘要作为 [alt] 文本，用远程 URL 替代原来的本地路径 ![](images/677a08ee041965bbbdb6b483d6c17d5aaa36a26b6dc96870a2019f0307b8616f.jpg)
            pattern = re.compile(
                r"!\[.*?\]\(.*?"
                + re.escape(images_with_summary_and_url.get("image_name"))
                + r"\)"
            )
            md_content = pattern.sub(
                lambda x: (
                    f"![{images_with_summary_and_url.get('summary')}]({images_with_summary_and_url.get('image_url')})"
                ),
                md_content,
            )
        # 将替换后的新内容写入新文件
        new_md_path_obj = md_path_obj.parent / f"{md_path_obj.stem}_new.md"
        with open(new_md_path_obj, "w", encoding="utf-8") as f:
            f.write(md_content)
        return md_content, new_md_path_obj

    def process(self, state: ImportGraphState):
        # 1. 校验MD文件路径和内容的有效性，获取MD文件内容和路径对象
        md_content, md_path_obj = self.check_and_get_md_content(state)

        # 2. 校验图片目录是否存在且有图片，获取图片目录路径和图片文件名列表
        result = self.check_images_dir_and_content(md_content, md_path_obj)
        if result is None:
            return {"md_content": md_content}
        images_dir_path_obj, images_dir_content_list = result

        # 3. 遍历图片列表，校验格式和引用关系，提取每张图片在MD中的上下文（前后250字）
        images_with_content_list = self.get_images_with_content_list(
            images_dir_content_list, images_dir_path_obj, md_content
        )
        if not images_with_content_list:
            logger.warning("无有效图片需要处理")
            return {"md_content": md_content}

        # 4. 调用VLM多模态模型为每张图片生成中文摘要（含滑动窗口限流）
        images_with_summary_list = self.get_images_with_summary_list(
            images_with_content_list
        )

        # 5. 上传图片到minio，替换原文的图片地址为minio的地址
        images_with_summary_and_url_list = self.get_image_with_summary_and_url_list(
            images_with_summary_list
        )

        # 6. 替换完成把新的内容存入物理文件，下一个节点测试使用
        md_content, new_md_path_obj = self.replace_md_images(
            md_content, md_path_obj, images_with_summary_and_url_list
        )
        return {"md_content": md_content, "md_path": new_md_path_obj}


if __name__ == "__main__":
    node = NodeMDImg()
    state = {"md_path": r"D:\data\output\hak180产品安全手册\hak180产品安全手册.md"}
    res = node(state)
    logger.info(res)

"""
输入：md_path    # MarkDown文件路径
输出：md_content    # MarkDown文件内容
问题1：
    查看图片是否被md引用，粗过滤，避免后续正则匹配的开销，这里边可能会包含没有被正确引用的，知识包含了image_name字符串
    再细过滤，查看是否被正确引用
    正则搜索要先编译模式、再逐字符扫描，开销明显更大
问题2：
    算法滑动门这块，current_time = time.time()  要放到循环内

总结1：dq = deque(maxlen=30) 滑动门的maxlen一般设置多少？
    查文档拿官方值，比如官方说 60 RPM
    实际设置打个 8 折，比如设 48，留点余量避免偶发超限
    如果窗口不是 60 秒而是其他值，下面 > 60 的窗口时间也要同步改
    一句话：maxlen 不是拍脑袋定的，是根据你要调的 API 的限流规则来的







## 2. 节点业务流程

### 2.1 节点作用

实现文档的“多模态语义对齐”。

### 2.2 实现思路

1.  **图文解耦与持久化**： 将图片从本地文件系统迁移到 MinIO 对象存储，实现计算节点与存储分离，确保知识库在不同环境下的可访问性。
2.  **语义增强**：引入 qwen3-vl-flash 或其他 VLM 模型（多模态模型），对每张图片进行“看图说话”，将视觉信息转化为文本摘要。这使得原本不可被搜索的图片，能够通过文本语义被检索到（如搜索“架构图”能找到对应的图片）。
3.  **速率控制**： 在调用 VLM API 时加入速率限制（Rate Limit），防止因图片过多触发并发风控。

### 2.3 步骤分解

本节点负责处理 Markdown 文件中的图片，实现多模态信息的融合。

1.  **初始化与上下文获取**： 从 `state` 中读取 Markdown 文件路径和内容。
2.  **获取图片列表携带上下文**： 扫描 Markdown 中引用的本地图片，得到图片的上下文。
3.  **获取图片列表携带总结摘要**： 使用多模态大模型（如 qwen3-vl-flash 或其他 VL 模型）对图片生成中文摘要。为了避免 API 限流，实现了令牌桶算法进行速率控制（Rate Limit）。
4.  **上传图片获取图片列表携带真实url地址**:：
    *   清理 MinIO 中对应的旧图片目录。
    *   将图片批量上传到 MinIO 对象存储。
5.  **替换内容图片的摘要和地址及备份文件**: 将 Markdown 中的本地图片路径替换为 MinIO 的 HTTP URL，并将生成的图片摘要填入 Markdown 图片的 Alt 文本中。将处理后的内容保存为 `_new.md` 文件，并更新 `state` 中的路径。
"""
