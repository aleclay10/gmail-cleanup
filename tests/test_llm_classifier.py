from unittest.mock import patch, MagicMock

import pytest
import requests
import responses

from llm_classifier import check_ollama_available, classify_email, classify_batch
from config import OLLAMA_URL, OLLAMA_MODEL


class TestCheckOllamaAvailable:
    @responses.activate
    def test_success(self):
        responses.add(
            responses.GET,
            f"{OLLAMA_URL}/api/tags",
            json={"models": [{"name": OLLAMA_MODEL}]},
            status=200,
        )
        ok, msg = check_ollama_available()
        assert ok is True
        assert msg == "OK"

    @responses.activate
    def test_connection_refused(self):
        responses.add(
            responses.GET,
            f"{OLLAMA_URL}/api/tags",
            body=requests.ConnectionError("Connection refused"),
        )
        ok, msg = check_ollama_available()
        assert ok is False
        assert "Cannot connect" in msg

    @responses.activate
    def test_model_not_found(self):
        responses.add(
            responses.GET,
            f"{OLLAMA_URL}/api/tags",
            json={"models": [{"name": "other-model"}]},
            status=200,
        )
        ok, msg = check_ollama_available()
        assert ok is False
        assert "not found" in msg


class TestClassifyEmail:
    @responses.activate
    def test_important_response(self):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            json={"message": {"content": "IMPORTANT"}},
            status=200,
        )
        result = classify_email("alice@test.com", "Meeting", "Let's meet")
        assert result == "important"

    @responses.activate
    def test_unimportant_response(self):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            json={"message": {"content": "UNIMPORTANT"}},
            status=200,
        )
        result = classify_email("shop@test.com", "Sale!", "50% off")
        assert result == "low_priority"

    @responses.activate
    def test_gibberish_defaults_to_important(self):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            json={"message": {"content": "I don't know what to say"}},
            status=200,
        )
        result = classify_email("x@test.com", "Test", "Body")
        assert result == "important"

    @responses.activate
    def test_http_error_defaults_to_important(self):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            json={"error": "server error"},
            status=500,
        )
        result = classify_email("x@test.com", "Test", "Body")
        assert result == "important"

    @responses.activate
    def test_timeout_defaults_to_important(self):
        responses.add(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            body=requests.exceptions.ReadTimeout("timeout"),
        )
        result = classify_email("x@test.com", "Test", "Body")
        assert result == "important"

    @responses.activate
    def test_snippet_truncation(self):
        long_snippet = "A" * 500
        captured_body = []

        def request_callback(request):
            import json
            captured_body.append(json.loads(request.body))
            return (200, {}, '{"message": {"content": "IMPORTANT"}}')

        responses.add_callback(
            responses.POST,
            f"{OLLAMA_URL}/api/chat",
            callback=request_callback,
        )

        classify_email("x@test.com", "Test", long_snippet)

        user_msg = captured_body[0]["messages"][1]["content"]
        # The snippet in the prompt should be truncated to 200 chars
        assert "A" * 200 in user_msg
        assert "A" * 201 not in user_msg


class TestClassifyBatch:
    @responses.activate
    def test_processes_list(self, sample_emails):
        for _ in sample_emails:
            responses.add(
                responses.POST,
                f"{OLLAMA_URL}/api/chat",
                json={"message": {"content": "IMPORTANT"}},
                status=200,
            )

        results = classify_batch(sample_emails)
        assert len(results) == 3
        assert all(v == "important" for v in results.values())
        assert set(results.keys()) == {"msg001", "msg002", "msg003"}
