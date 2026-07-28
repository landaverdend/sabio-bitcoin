from unittest.mock import patch

from backend import irc


def test_event_detail_fetches_archived_irc_event():
    response = {
        "id": "irc_event:42",
        "channel": "bitcoin-core-dev",
        "body": "hello",
    }
    with patch.object(irc, "get_irc_event", return_value=response) as get_irc_event:
        result = irc.event_detail("irc_event:42", "anon:test")

    assert result == response
    get_irc_event.assert_called_once_with("irc_event:42")
