from upload_service.review_service import ReviewService


def test_rejected_cleanup_matches_same_batch_selected_targets():
    base = {
        "id": "r1",
        "timestamp": "2026-05-07T10:00:00+08:00",
        "reject_reason": "缺少说明",
        "uploader": "alice",
        "selected_dbs": ["db_a"],
        "source_collection": "db_a",
        "data": {
            "object": "模块A",
            "reply_logic": "逻辑",
            "feature_explanation": "说明",
            "image_url": ["/old.png"],
            "file_url": ["/old.pdf"],
        },
    }
    sibling = {
        **base,
        "id": "r2",
        "selected_dbs": ["db_b"],
        "source_collection": "db_b",
    }
    other_target = {
        **base,
        "id": "r3",
        "selected_dbs": ["db_c"],
        "source_collection": "db_c",
    }

    cleanup_ids = ReviewService._same_batch_rejected_ids(
        records=[base, sibling, other_target],
        source_record=base,
        selected_dbs=["db_a", "db_b"],
    )

    assert cleanup_ids == {"r1", "r2"}


def test_rejected_cleanup_does_not_match_different_timestamp():
    source = {
        "id": "r1",
        "timestamp": "2026-05-07T10:00:00+08:00",
        "reject_reason": "缺少说明",
        "uploader": "alice",
        "selected_dbs": ["db_a"],
        "source_collection": "db_a",
        "data": {"object": "模块A", "reply_logic": "逻辑", "feature_explanation": "说明"},
    }
    other_batch = {
        **source,
        "id": "r2",
        "timestamp": "2026-05-07T11:00:00+08:00",
        "selected_dbs": ["db_b"],
        "source_collection": "db_b",
    }

    cleanup_ids = ReviewService._same_batch_rejected_ids(
        records=[source, other_batch],
        source_record=source,
        selected_dbs=["db_a", "db_b"],
    )

    assert cleanup_ids == {"r1"}


def test_rejected_cleanup_ignores_attachment_changes():
    source = {
        "id": "r1",
        "timestamp": "2026-05-07T10:00:00+08:00",
        "reject_reason": "缺少说明",
        "uploader": "alice",
        "selected_dbs": ["db_a"],
        "source_collection": "db_a",
        "data": {
            "object": "模块A",
            "reply_logic": "逻辑",
            "feature_explanation": "说明",
            "image_url": ["/a.png"],
            "file_url": ["/a.pdf"],
        },
    }
    sibling = {
        **source,
        "id": "r2",
        "selected_dbs": ["db_b"],
        "source_collection": "db_b",
        "data": {
            "object": "模块A",
            "reply_logic": "逻辑",
            "feature_explanation": "说明",
            "image_url": ["/different.png"],
            "file_url": ["/different.pdf"],
        },
    }

    cleanup_ids = ReviewService._same_batch_rejected_ids(
        records=[source, sibling],
        source_record=source,
        selected_dbs=["db_a", "db_b"],
    )

    assert cleanup_ids == {"r1", "r2"}


def test_find_rejected_record_returns_none_for_missing_id():
    records = [{"id": "existing"}]

    found = ReviewService._find_rejected_record(records, "missing")

    assert found is None
