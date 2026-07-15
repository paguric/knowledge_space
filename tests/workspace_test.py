import json

from knowledge_base.workspace import Workspace


def test_json_serialization_roundtrip(ks_env, test_ws):
    ws_dict = test_ws.to_dict()
    json_str = json.dumps(ws_dict, indent=2)

    loaded_data = json.loads(json_str)
    restored_ws = Workspace.from_dict(loaded_data)
    assert restored_ws.to_dict() == test_ws.to_dict()
