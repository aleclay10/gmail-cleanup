import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from gmail_auth import get_gmail_service


@pytest.fixture
def mock_creds():
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "refresh"
    creds.to_json.return_value = '{"token": "test"}'
    return creds


class TestGetGmailService:
    @patch("gmail_auth.build")
    @patch("gmail_auth.Credentials.from_authorized_user_file")
    @patch("gmail_auth.os.path.exists")
    def test_valid_token_loads_service(self, mock_exists, mock_from_file, mock_build, mock_creds):
        mock_exists.return_value = True
        mock_from_file.return_value = mock_creds
        mock_build.return_value = MagicMock()

        service = get_gmail_service()

        mock_from_file.assert_called_once()
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_creds)
        assert service is not None

    @patch("gmail_auth.build")
    @patch("gmail_auth.Credentials.from_authorized_user_file")
    @patch("gmail_auth.os.path.exists")
    def test_expired_token_refreshes(self, mock_exists, mock_from_file, mock_build, mock_creds):
        mock_creds.valid = False
        mock_creds.expired = True
        mock_exists.return_value = True
        mock_from_file.return_value = mock_creds

        with patch("builtins.open", mock_open()):
            get_gmail_service()

        mock_creds.refresh.assert_called_once()

    @patch("gmail_auth.build")
    @patch("gmail_auth.InstalledAppFlow.from_client_secrets_file")
    @patch("gmail_auth.os.path.exists")
    def test_no_token_triggers_browser_flow(self, mock_exists, mock_flow_cls, mock_build):
        # First call: token file doesn't exist; second call: client_secret exists
        mock_exists.side_effect = [False, True]

        flow = MagicMock()
        creds = MagicMock()
        creds.valid = True
        creds.to_json.return_value = '{"token": "new"}'
        flow.run_local_server.return_value = creds
        mock_flow_cls.return_value = flow

        with patch("builtins.open", mock_open()):
            get_gmail_service()

        flow.run_local_server.assert_called_once_with(port=0)

    @patch("gmail_auth.os.path.exists")
    def test_missing_client_secret_raises(self, mock_exists):
        mock_exists.return_value = False  # both token and client_secret missing

        with pytest.raises(FileNotFoundError, match="client_secret"):
            get_gmail_service()

    @patch("gmail_auth.build")
    @patch("gmail_auth.InstalledAppFlow.from_client_secrets_file")
    @patch("gmail_auth.os.path.exists")
    def test_token_saved_after_fresh_auth(self, mock_exists, mock_flow_cls, mock_build):
        mock_exists.side_effect = [False, True]

        flow = MagicMock()
        creds = MagicMock()
        creds.valid = True
        creds.to_json.return_value = '{"token": "saved"}'
        flow.run_local_server.return_value = creds
        mock_flow_cls.return_value = flow

        m = mock_open()
        with patch("builtins.open", m):
            get_gmail_service()

        # Verify token was written
        m().write.assert_called_once_with('{"token": "saved"}')
