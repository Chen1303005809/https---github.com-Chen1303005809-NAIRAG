import sys
import types


fake_utils = types.ModuleType("utils.utils")
fake_utils.embedding = lambda payload: []
sys.modules.setdefault("utils.utils", fake_utils)

fake_services = types.ModuleType("milvus_admin.backend.services")
fake_services.get_services = lambda app: None
sys.modules.setdefault("milvus_admin.backend.services", fake_services)

from milvus_admin.backend.data_routes import _build_doc_uploader_map


def test_build_doc_uploader_map_from_single_approve_log():
    logs = [
        {
            "type": "approve",
            "user": "admin",
            "doc_id": "doc-1",
            "uploader": "alice",
        }
    ]

    assert _build_doc_uploader_map(logs) == {"doc-1": "alice"}


def test_build_doc_uploader_map_from_batch_approve_log():
    logs = [
        {
            "type": "approve",
            "user": "admin",
            "doc_ids": ["doc-1", "doc-2"],
            "uploaders": ["alice", "bob"],
        }
    ]

    assert _build_doc_uploader_map(logs) == {"doc-1": "alice", "doc-2": "bob"}


def test_build_doc_uploader_map_falls_back_to_single_uploader_for_batch():
    logs = [
        {
            "type": "approve",
            "doc_ids": ["doc-1", "doc-2"],
            "uploader": "alice",
        }
    ]

    assert _build_doc_uploader_map(logs) == {"doc-1": "alice", "doc-2": "alice"}
