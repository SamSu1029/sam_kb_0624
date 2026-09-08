"""
    @Author:Sam
    @Time:2026/9/5
    @Desc:
"""
from kb_main.import_process.base import NodeBase
from kb_main.import_process.state import ImportGraphState
from kb_main.tool.logger import logger


class TestBase(NodeBase):
    name = "test_base"

    def process(self, state):
        logger.info("test_base执行中")
        return state

if __name__ == '__main__':
    test_base=TestBase()
    init_state={"task_id":"abc"}
    init_state=ImportGraphState(init_state)
    res=test_base(init_state)
    logger.info(res)