from unittest.mock import patch

from backend import comms


def test_message_detail_fetches_archived_message():
    response = {"id": 42, "channel": "mailing_list", "body": "hello"}
    with patch.object(comms, "get_message", return_value=response) as get_message:
        result = comms.message_detail(42, "anon:test")

    assert result == response
    get_message.assert_called_once_with("message:42")
