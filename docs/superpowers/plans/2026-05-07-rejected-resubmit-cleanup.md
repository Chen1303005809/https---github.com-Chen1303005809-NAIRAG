# Rejected Resubmit Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user edit one rejected record, choose multiple vector stores, resubmit once, and automatically remove matching same-batch rejected records.

**Architecture:** Keep the existing one-record-per-target-review-file model. Add backend helpers in `upload_service/review_service.py` to load the source rejected record, compute same-batch cleanup IDs, write new pending records, then delete only matched rejected records after the pending file is saved. Frontend behavior already supports multi-select resubmission, so UI changes are optional and limited to copy/status text.

**Tech Stack:** Python 3.12, FastAPI service code, JSON file storage, existing upload dashboard JavaScript.

---

## File Structure

- Modify `upload_service/review_service.py`
  - Add data normalization helpers for comparing rejected record payloads.
  - Add helpers to find the source rejected record and same-batch cleanup IDs.
  - Update `resubmit_rejected` to 404 when `old_record_id` is missing and to delete matched records after successful pending-file write.
- Optionally modify `web/upload/upload_dashboard.html`
  - Keep existing multi-select UI.
  - Update success message if desired to say old same-batch rejected records were cleared.
- Optional create `tests/test_review_service_rejected_cleanup.py`
  - Unit-test pure cleanup matching helpers without requiring the web server.
  - Use Python 3.12 in the project virtual environment when runnable.

## Task 1: Add Same-Batch Matching Helpers

**Files:**
- Modify: `upload_service/review_service.py`
- Optional Test: `tests/test_review_service_rejected_cleanup.py`

- [ ] **Step 1: Write helper tests first**

Create `tests/test_review_service_rejected_cleanup.py` with focused tests for the matching behavior:

```python
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
```

```python
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
```

```python
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
```

- [ ] **Step 2: Run tests to verify RED when possible**

Run from the project root in the Python 3.12 virtual environment:

```bash
. .venv/bin/activate
python --version
pytest tests/test_review_service_rejected_cleanup.py -v
```

Expected before implementation: tests fail because `ReviewService._same_batch_rejected_ids` does not exist.

If the current environment cannot execute Python services, skip execution and record that these tests are unrun.

- [ ] **Step 3: Add helper implementation**

In `upload_service/review_service.py`, add these methods inside `ReviewService` after `_sort_rejected_records`:

```python
    @staticmethod
    def _record_target_dbs(record: dict) -> set[str]:
        targets = set()
        source_collection = str((record or {}).get("source_collection") or "").strip()
        if source_collection:
            targets.add(source_collection)
        for db in (record or {}).get("selected_dbs", []) or []:
            clean = str(db or "").strip()
            if clean:
                targets.add(clean)
        return targets

    @staticmethod
    def _comparable_rejected_data(record: dict) -> dict:
        data = dict((record or {}).get("data") or {})
        data.pop("image_url", None)
        data.pop("file_url", None)
        return data

    @classmethod
    def _same_batch_rejected_ids(
        cls,
        records: list[dict],
        source_record: dict,
        selected_dbs: list[str],
    ) -> set[str]:
        selected = {str(db or "").strip() for db in selected_dbs if str(db or "").strip()}
        source_timestamp = str((source_record or {}).get("timestamp") or "").strip()
        source_reason = str((source_record or {}).get("reject_reason") or "").strip()
        source_uploader = str((source_record or {}).get("uploader") or "").strip()
        source_data = cls._comparable_rejected_data(source_record)

        cleanup_ids = set()
        for record in records or []:
            record_id = str((record or {}).get("id") or "").strip()
            if not record_id:
                continue
            if source_uploader and str((record or {}).get("uploader") or "").strip() != source_uploader:
                continue
            if str((record or {}).get("reject_reason") or "").strip() != source_reason:
                continue
            record_timestamp = str((record or {}).get("timestamp") or "").strip()
            if source_timestamp and record_timestamp and record_timestamp != source_timestamp:
                continue
            if cls._comparable_rejected_data(record) != source_data:
                continue
            if not (cls._record_target_dbs(record) & selected):
                continue
            cleanup_ids.add(record_id)

        source_id = str((source_record or {}).get("id") or "").strip()
        if source_id:
            cleanup_ids.add(source_id)
        return cleanup_ids
```

- [ ] **Step 4: Run helper tests to verify GREEN when possible**

Run:

```bash
. .venv/bin/activate
pytest tests/test_review_service_rejected_cleanup.py -v
```

Expected after implementation: all helper tests pass. If execution is unavailable, mark tests as not run and rely on code review plus manual acceptance.

## Task 2: Update Resubmission Cleanup Flow

**Files:**
- Modify: `upload_service/review_service.py`
- Optional Test: `tests/test_review_service_rejected_cleanup.py`

- [ ] **Step 1: Add a test for missing rejected record**

Append this test if automated tests are being maintained:

```python
def test_find_rejected_record_returns_none_for_missing_id():
    records = [{"id": "existing"}]

    found = ReviewService._find_rejected_record(records, "missing")

    assert found is None
```

- [ ] **Step 2: Add lookup and bulk delete helpers**

In `upload_service/review_service.py`, add these methods near `_delete_rejected_by_id`:

```python
    @staticmethod
    def _find_rejected_record(records: list[dict], record_id: str) -> Optional[dict]:
        for record in records or []:
            if str((record or {}).get("id")) == str(record_id):
                return record
        return None

    def _delete_rejected_by_ids(self, uploader: str, record_ids: set[str]):
        if not record_ids:
            return
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            return
        records = self._load_json(rejected_file, [])
        cleaned = [r for r in records if str(r.get("id")) not in record_ids]
        if cleaned:
            self._save_json(rejected_file, cleaned)
        else:
            os.remove(rejected_file)
```

- [ ] **Step 3: Update `resubmit_rejected` before file uploads**

In `resubmit_rejected`, after permission validation and before parsing/uploading files, load and validate the source rejected record:

```python
        rejected_file = os.path.join(self.config.rejected_dir, f"{uploader}.json")
        if not os.path.exists(rejected_file):
            raise HTTPException(status_code=404, detail="记录不存在")
        rejected_records = self._load_json(rejected_file, [])
        source_rejected = self._find_rejected_record(rejected_records, old_record_id)
        if not source_rejected:
            raise HTTPException(status_code=404, detail="记录未找到，可能已被处理")
```

- [ ] **Step 4: Replace single-record deletion with same-batch deletion**

At the end of `resubmit_rejected`, replace:

```python
        self._delete_rejected_by_id(uploader=uploader, record_id=old_record_id)
```

with:

```python
        cleanup_ids = self._same_batch_rejected_ids(
            records=rejected_records,
            source_record=source_rejected,
            selected_dbs=selected,
        )
        self._delete_rejected_by_ids(uploader=uploader, record_ids=cleanup_ids)
```

Keep this after `_save_json(os.path.join(self.config.review_dir, filename), final_records)` so failed pending-file writes do not remove rejected records.

- [ ] **Step 5: Run targeted tests when possible**

Run:

```bash
. .venv/bin/activate
pytest tests/test_review_service_rejected_cleanup.py -v
```

Expected: helper and lookup tests pass. If execution is unavailable, mark unrun.

## Task 3: Optional Frontend Copy Update

**Files:**
- Modify: `web/upload/upload_dashboard.html`

- [ ] **Step 1: Update success text only if desired**

In `submitResubmission`, replace:

```javascript
    document.getElementById('editStatus').textContent = '重提成功';
```

with:

```javascript
    document.getElementById('editStatus').textContent = data.message || '重提成功';
```

This keeps behavior unchanged while surfacing backend wording.

- [ ] **Step 2: Keep the multi-select UI unchanged**

Do not change `openRejectedEdit` or `#editDbChecks` unless manual testing shows users miss the multi-select control. The current UI already renders checkboxes and posts all selected values.

## Task 4: Manual Acceptance Test

**Files:**
- No code changes.

- [ ] **Step 1: Prepare three same-batch rejected records**

In the running app, upload one record with three target vector stores selected. Have the admin reject all three pending records with the same rejection reason.

- [ ] **Step 2: Resubmit from one rejected record**

Log in as the uploader, open the rejected records modal, edit any one of the three records, choose the same three target vector stores, and confirm resubmission.

- [ ] **Step 3: Verify user-side cleanup**

Reopen the rejected records modal. Expected: the three old same-batch rejected records are gone. Any unrelated rejected records remain.

- [ ] **Step 4: Verify admin-side pending records**

Open the admin review page. Expected: three new pending records exist, one per selected vector store, each containing the edited content.

- [ ] **Step 5: Verify partial target behavior**

Repeat with three same-batch rejected records, but resubmit to only two target vector stores. Expected: the two matched old rejected records are cleared, and the unselected target store's rejected record remains.

- [ ] **Step 6: Verify no cross-batch deletion**

Create another rejected record with the same content but a different upload time. Resubmit the first batch. Expected: the different-timestamp record remains.

## Task 5: Review and Commit

**Files:**
- Review all changed files.

- [ ] **Step 1: Inspect diff**

Run:

```bash
git diff -- upload_service/review_service.py web/upload/upload_dashboard.html tests/test_review_service_rejected_cleanup.py
```

Expected: changes are limited to rejected resubmission cleanup, optional UI copy, and optional tests.

- [ ] **Step 2: Run static syntax check when possible**

Run:

```bash
. .venv/bin/activate
python -m py_compile upload_service/review_service.py
```

Expected: command exits with status 0. If execution is unavailable, record it as not run.

- [ ] **Step 3: Commit implementation**

Run:

```bash
git add upload_service/review_service.py web/upload/upload_dashboard.html tests/test_review_service_rejected_cleanup.py
git commit -m "fix: clear same-batch rejected records on resubmit"
```

If the optional frontend or test file was not changed, omit it from `git add`.
