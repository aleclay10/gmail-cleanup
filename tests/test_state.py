import json
import os

import pytest

from state import RunState


class TestRunStateInit:
    def test_default_init(self):
        state = RunState()
        assert state.all_message_ids == []
        assert state.processed == {}
        assert state.labeled == set()


class TestRunStateSaveLoad:
    def test_save_creates_file(self, tmp_checkpoint):
        state = RunState(all_message_ids=["a", "b"])
        state.save()
        assert os.path.exists(tmp_checkpoint)

    def test_load_reads_saved_data(self, tmp_checkpoint):
        state = RunState(
            all_message_ids=["a", "b"],
            processed={"a": "important"},
            labeled={"a"},
        )
        state.save()

        loaded = RunState.load()
        assert loaded is not None
        assert loaded.all_message_ids == ["a", "b"]
        assert loaded.processed == {"a": "important"}
        assert loaded.labeled == {"a"}

    def test_load_returns_none_when_no_file(self, tmp_checkpoint):
        assert RunState.load() is None

    def test_load_handles_missing_labeled_key(self, tmp_checkpoint):
        data = {"all_message_ids": ["x"], "processed": {"x": "important"}}
        with open(tmp_checkpoint, "w") as f:
            json.dump(data, f)

        loaded = RunState.load()
        assert loaded.labeled == set()

    def test_round_trip_with_set_serialization(self, tmp_checkpoint):
        state = RunState(
            all_message_ids=["1", "2", "3"],
            processed={"1": "important", "2": "low_priority"},
            labeled={"1", "2"},
        )
        state.save()
        loaded = RunState.load()

        assert loaded.all_message_ids == state.all_message_ids
        assert loaded.processed == state.processed
        assert loaded.labeled == state.labeled

    def test_atomic_write_uses_tmp_file(self, tmp_checkpoint, monkeypatch):
        """Verify .tmp file is used during save (atomic write via os.replace)."""
        replaced = []
        original_replace = os.replace

        def tracking_replace(src, dst):
            replaced.append((src, dst))
            return original_replace(src, dst)

        monkeypatch.setattr("os.replace", tracking_replace)
        RunState().save()

        assert len(replaced) == 1
        assert replaced[0][0].endswith(".tmp")
        assert replaced[0][1] == tmp_checkpoint


class TestRunStateClear:
    def test_clear_removes_file(self, tmp_checkpoint):
        RunState().save()
        assert os.path.exists(tmp_checkpoint)
        RunState.clear()
        assert not os.path.exists(tmp_checkpoint)

    def test_clear_no_op_when_missing(self, tmp_checkpoint):
        RunState.clear()  # should not raise
