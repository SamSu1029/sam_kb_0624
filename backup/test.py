# test/GPU验证.py

import torch

print('=== GPU 信息检测 ===')
print(f'GPU 可用：{torch.cuda.is_available()}')

if torch.cuda.is_available():
    # 获取显卡数量
    gpu_count = torch.cuda.device_count()
    print(f'显卡数量：{gpu_count}')

    # 遍历每块显卡的详细信息
    for i in range(gpu_count):
        print(f'\n--- 显卡 {i} ---')
        print(f'名称：{torch.cuda.get_device_name(i)}')
        print(f'计算能力：{torch.cuda.get_device_capability(i)}')

        # 获取显存信息（单位：GB）
        total_memory = torch.cuda.get_device_properties(i).total_memory / (1024**3)
        print(f'总显存：{total_memory:.2f} GB')

        # 当前显存使用情况
        allocated = torch.cuda.memory_allocated(i) / (1024**3)
        reserved = torch.cuda.memory_reserved(i) / (1024**3)
        print(f'已分配显存：{allocated:.2f} GB')
        print(f'已预留显存：{reserved:.2f} GB')

        # CUDA 版本
        print(f'CUDA 版本：{torch.version.cuda}')
        print(f'cuDNN 版本：{torch.backends.cudnn.version()}')
else:
    print('未检测到可用的 GPU，将使用 CPU')


import re


def split_md_by_heading(md_line_list):
    """
    按 Markdown 标题切分文档。

    参数:
        md_line_list: 按换行符切分后的字符串列表

    返回:
        sections: 每个元素都是“标题 + 标题下内容”的完整字符串
    """
    # 匹配 # 标题、## 标题……最多支持六级标题
    heading_pattern = re.compile(r"^\s{0,3}#{1,6}(?:\s+|$)")

    sections = []
    current_section = []
    in_code_block = False

    for line in md_line_list:
        # 避免把代码块中的 "# ..." 误判为标题
        if re.match(r"^\s*(```|~~~)", line):
            in_code_block = not in_code_block

        is_heading = (
            not in_code_block
            and heading_pattern.match(line) is not None
        )

        if is_heading:
            # 遇到新标题时，保存前一个标题章节
            if current_section:
                sections.append("\n".join(current_section).strip())

            current_section = [line]
        elif current_section:
            # 只收集已经找到标题后的内容
            current_section.append(line)

    # 保存最后一个章节
    if current_section:
        sections.append("\n".join(current_section).strip())

    return sections