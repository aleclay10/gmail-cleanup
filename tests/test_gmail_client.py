from unittest.mock import MagicMock, call

import pytest

from gmail_client import GmailClient


@pytest.fixture
def client(mock_gmail_service):
    return GmailClient(mock_gmail_service)


class TestFetchMessageIds:
    def test_single_page(self, client, mock_gmail_service):
        mock_gmail_service.users().messages().list().execute.return_value = {
            "messages": [{"id": "a"}, {"id": "b"}],
        }

        ids = client.fetch_message_ids("is:unread")
        assert ids == ["a", "b"]

    def test_multi_page_pagination(self, client, mock_gmail_service):
        list_mock = mock_gmail_service.users().messages().list().execute
        list_mock.side_effect = [
            {"messages": [{"id": "a"}], "nextPageToken": "tok2"},
            {"messages": [{"id": "b"}]},
        ]

        ids = client.fetch_message_ids("is:unread")
        assert ids == ["a", "b"]

    def test_empty_result(self, client, mock_gmail_service):
        mock_gmail_service.users().messages().list().execute.return_value = {}

        ids = client.fetch_message_ids("is:unread")
        assert ids == []


class TestFetchMessageDetailsBatch:
    def test_extracts_headers(self, client, mock_gmail_service):
        batch_mock = MagicMock()
        pending = []

        def fake_add(request, callback, request_id):
            response = {
                "id": request_id,
                "payload": {
                    "headers": [
                        {"name": "From", "value": "alice@test.com"},
                        {"name": "Subject", "value": "Hello"},
                        {"name": "Date", "value": "2025-01-01"},
                    ]
                },
                "snippet": "Preview text",
            }
            pending.append((request_id, response, callback))

        def fake_execute():
            for req_id, response, cb in pending:
                cb(req_id, response, None)
            pending.clear()

        batch_mock.add.side_effect = fake_add
        batch_mock.execute.side_effect = fake_execute
        mock_gmail_service.new_batch_http_request.return_value = batch_mock

        results = client.fetch_message_details_batch(["msg1"])
        assert "msg1" in results
        assert results["msg1"]["from"] == "alice@test.com"
        assert results["msg1"]["subject"] == "Hello"
        assert results["msg1"]["date"] == "2025-01-01"
        assert results["msg1"]["snippet"] == "Preview text"

    def test_handles_batch_errors(self, client, mock_gmail_service):
        batch_mock = MagicMock()
        pending = []

        def fake_add(request, callback, request_id):
            pending.append((request_id, callback))

        def fake_execute():
            for req_id, cb in pending:
                cb(req_id, None, Exception("API error"))
            pending.clear()

        batch_mock.add.side_effect = fake_add
        batch_mock.execute.side_effect = fake_execute
        mock_gmail_service.new_batch_http_request.return_value = batch_mock

        results = client.fetch_message_details_batch(["msg1"])
        assert results == {}


class TestEnsureLabelsExist:
    def test_labels_already_exist(self, client, mock_gmail_service):
        mock_gmail_service.users().labels().list().execute.return_value = {
            "labels": [
                {"name": "AI/Important", "id": "Label_1"},
                {"name": "AI/Low Priority", "id": "Label_2"},
            ]
        }

        client.ensure_labels_exist()

        assert client.get_label_id("AI/Important") == "Label_1"
        assert client.get_label_id("AI/Low Priority") == "Label_2"
        mock_gmail_service.users().labels().create.assert_not_called()

    def test_labels_missing_creates_them(self, client, mock_gmail_service):
        mock_gmail_service.users().labels().list().execute.return_value = {"labels": []}
        mock_gmail_service.users().labels().create().execute.side_effect = [
            {"id": "New_1"},
            {"id": "New_2"},
        ]

        client.ensure_labels_exist()

        assert client.get_label_id("AI/Important") == "New_1"
        assert client.get_label_id("AI/Low Priority") == "New_2"


class TestApplyLabelBatch:
    def test_calls_modify(self, client, mock_gmail_service):
        batch_mock = MagicMock()
        mock_gmail_service.new_batch_http_request.return_value = batch_mock

        client.apply_label_batch(["msg1", "msg2"], "Label_1")

        assert batch_mock.add.call_count == 2
        batch_mock.execute.assert_called_once()
