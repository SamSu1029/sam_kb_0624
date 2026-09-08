import json


def json_format(data):
    return json.dumps(data,ensure_ascii=False,indent=4)