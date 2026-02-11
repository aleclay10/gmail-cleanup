import os
import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from classifier_engine import ClassifierEngine
from state import RunState


@pytest.fixture
def engine_deps(mock_gmail_service, tmp_checkpoint, tmp_path, monkeypatch):
    """Set up a ClassifierEngine with mocked dependencies."""
    report_file = str(tmp_path / "report.html")
    monkeypatch.setattr("classifier_engine.REPORT_FILE", report_file)

    logs = []
    progress = []

    engine = ClassifierEngine(
        service=mock_gmail_service,
        progress_cb=lambda done, total, cls: progress.append((done, total, cls)),
        log_cb=lambda msg: logs.append(msg),
        query="is:unread",
    )
    return engine, logs, progress, report_file


class TestClassifierEnginePipeline:
    @patch("classifier_engine.classify_batch")
    def test_fresh_run(self, mock_classify_batch, engine_deps, mock_gmail_service):
        engine, logs, progress, report_file = engine_deps

        # Setup mocks
        mock_classify_batch.return_value = {"m1": "important", "m2": "important"}

        # fetch_message_ids returns 2 messages
        engine.gmail.fetch_message_ids = MagicMock(return_value=["m1", "m2"])

        # ensure_labels_exist
        engine.gmail.ensure_labels_exist = MagicMock()
        engine.gmail._label_ids = {"AI/Important": "L1", "AI/Low Priority": "L2"}

        # fetch_message_details_batch
        engine.gmail.fetch_message_details_batch = MagicMock(
            return_value={
                "m1": {"id": "m1", "from": "a@t.com", "subject": "Hi", "date": "2025-01-01", "snippet": "Hello"},
                "m2": {"id": "m2", "from": "b@t.com", "subject": "Bye", "date": "2025-01-01", "snippet": "Later"},
            }
        )

        # apply_label_batch
        engine.gmail.apply_label_batch = MagicMock()

        engine._pipeline(resume=False)

        mock_classify_batch.assert_called_once()
        engine.gmail.apply_label_batch.assert_called()
        assert os.path.exists(report_file)
        assert any("Done!" in msg for msg in logs)

    @patch("classifier_engine.classify_batch")
    def test_resume_with_checkpoint(self, mock_classify_batch, engine_deps, tmp_checkpoint):
        engine, logs, progress, report_file = engine_deps

        # Pre-save a checkpoint with one message already processed
        state = RunState(
            all_message_ids=["m1", "m2"],
            processed={"m1": "important"},
            labeled=set(),
        )
        state.save()

        mock_classify_batch.return_value = {"m2": "low_priority"}

        engine.gmail.ensure_labels_exist = MagicMock()
        engine.gmail._label_ids = {"AI/Important": "L1", "AI/Low Priority": "L2"}
        engine.gmail.fetch_message_details_batch = MagicMock(
            return_value={
                "m2": {"id": "m2", "from": "c@t.com", "subject": "Sale", "date": "2025-01-01", "snippet": "Buy now"},
            }
        )
        engine.gmail.apply_label_batch = MagicMock()

        engine._pipeline(resume=True)

        # Only m2 should have been classified (one batch call)
        assert mock_classify_batch.call_count == 1
        assert any("Resumed" in msg for msg in logs)

    @patch("classifier_engine.classify_batch")
    def test_resume_no_checkpoint_starts_fresh(self, mock_classify_batch, engine_deps, tmp_checkpoint):
        engine, logs, progress, report_file = engine_deps

        mock_classify_batch.return_value = {"m1": "important"}

        engine.gmail.fetch_message_ids = MagicMock(return_value=["m1"])
        engine.gmail.ensure_labels_exist = MagicMock()
        engine.gmail._label_ids = {"AI/Important": "L1", "AI/Low Priority": "L2"}
        engine.gmail.fetch_message_details_batch = MagicMock(
            return_value={
                "m1": {"id": "m1", "from": "a@t.com", "subject": "Hi", "date": "2025-01-01", "snippet": "Hello"},
            }
        )
        engine.gmail.apply_label_batch = MagicMock()

        engine._pipeline(resume=True)

        assert any("No checkpoint" in msg for msg in logs)

    @patch("classifier_engine.classify_batch")
    def test_stop_event_saves_checkpoint(self, mock_classify_batch, engine_deps, tmp_checkpoint):
        engine, logs, progress, report_file = engine_deps

        def classify_and_stop(emails, **kwargs):
            # After first batch completes, set stop event so next batch is skipped
            engine._stop_event.set()
            return {e["id"]: "important" for e in emails}

        mock_classify_batch.side_effect = classify_and_stop

        # Use 3 messages with BATCH_SIZE patched to 1 so we get multiple batches
        engine.gmail.fetch_message_ids = MagicMock(return_value=["m1", "m2", "m3"])
        engine.gmail.ensure_labels_exist = MagicMock()
        engine.gmail._label_ids = {"AI/Important": "L1", "AI/Low Priority": "L2"}

        def fake_fetch_details(ids):
            return {
                mid: {"id": mid, "from": f"{mid}@t.com", "subject": f"Subj {mid}", "date": "2025-01-01", "snippet": "text"}
                for mid in ids
            }

        engine.gmail.fetch_message_details_batch = MagicMock(side_effect=fake_fetch_details)

        with patch("classifier_engine.BATCH_SIZE", 1):
            engine._pipeline(resume=False)

        assert any("Stopped" in msg for msg in logs)
        # Checkpoint should exist (not cleared since we stopped mid-run)
        assert os.path.exists(tmp_checkpoint)

    @patch("classifier_engine.classify_batch")
    def test_empty_query_result(self, mock_classify_batch, engine_deps):
        engine, logs, progress, report_file = engine_deps

        engine.gmail.fetch_message_ids = MagicMock(return_value=[])
        engine.gmail.ensure_labels_exist = MagicMock()

        engine._pipeline(resume=False)

        assert any("No messages found" in msg for msg in logs)
        mock_classify_batch.assert_not_called()

    @patch("classifier_engine.classify_batch")
    def test_report_generation(self, mock_classify_batch, engine_deps):
        engine, logs, progress, report_file = engine_deps

        mock_classify_batch.return_value = {"m1": "important", "m2": "low_priority"}

        engine.gmail.fetch_message_ids = MagicMock(return_value=["m1", "m2"])
        engine.gmail.ensure_labels_exist = MagicMock()
        engine.gmail._label_ids = {"AI/Important": "L1", "AI/Low Priority": "L2"}

        details = {
            "m1": {"id": "m1", "from": "a@t.com", "subject": "Important email", "date": "2025-01-01", "snippet": "Hello"},
            "m2": {"id": "m2", "from": "b@t.com", "subject": "Spam stuff", "date": "2025-01-01", "snippet": "Buy now"},
        }
        engine.gmail.fetch_message_details_batch = MagicMock(return_value=details)
        engine.gmail.apply_label_batch = MagicMock()

        engine._pipeline(resume=False)

        assert os.path.exists(report_file)
        with open(report_file, encoding="utf-8") as f:
            html = f.read()
        assert "<strong>Important:</strong> 1" in html
        assert "<strong>Low Priority:</strong> 1" in html
        assert "Important email" in html
        assert "Spam stuff" in html

        # Report should use cached details, not re-fetch
        # fetch_message_details_batch called once for classification, not again for report
        assert engine.gmail.fetch_message_details_batch.call_count == 1
