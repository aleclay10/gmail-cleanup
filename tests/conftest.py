import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def tmp_checkpoint(tmp_path, monkeypatch):
    """Patch CHECKPOINT_FILE to a temporary path."""
    cp = str(tmp_path / "checkpoint.json")
    monkeypatch.setattr("config.CHECKPOINT_FILE", cp)
    monkeypatch.setattr("state.CHECKPOINT_FILE", cp)
    return cp


@pytest.fixture
def mock_gmail_service():
    """Mock Gmail API service with chainable method calls."""
    service = MagicMock()

    # users().messages().list().execute()
    messages = MagicMock()
    service.users.return_value.messages.return_value = messages

    # users().labels().list().execute()
    labels = MagicMock()
    service.users.return_value.labels.return_value = labels

    # new_batch_http_request()
    service.new_batch_http_request.return_value = MagicMock(spec=["add", "execute"])

    return service


@pytest.fixture
def sample_emails():
    """List of email metadata dicts for reuse."""
    return [
        {
            "id": "msg001",
            "from": "alice@example.com",
            "subject": "Meeting tomorrow",
            "date": "Mon, 1 Jan 2025 10:00:00 +0000",
            "snippet": "Let's meet at 3pm to discuss the project.",
        },
        {
            "id": "msg002",
            "from": "newsletter@shop.com",
            "subject": "50% off everything!",
            "date": "Mon, 1 Jan 2025 11:00:00 +0000",
            "snippet": "Big sale happening now. Don't miss out on these deals.",
        },
        {
            "id": "msg003",
            "from": "bob@company.com",
            "subject": "Invoice #1234",
            "date": "Mon, 1 Jan 2025 12:00:00 +0000",
            "snippet": "Please find attached your invoice for January.",
        },
    ]
