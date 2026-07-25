from datetime import datetime, timezone
from unittest.mock import patch

from backend import people


class TestListPeople:
    def test_total_comes_from_the_row_window_function_not_a_second_query(self):
        rows = [
            (1, "Alice", "alice@example.com", None, None, 5, 19744),
            (2, "Bob", None, "bob", None, 3, 19744),
        ]
        with patch.object(people, "run_query", return_value=rows) as run_query:
            result = people.list_people(page=1)

        # The whole point of count(*) OVER() is avoiding a second round trip
        # to Neon -- a regression here silently brings that cost back.
        run_query.assert_called_once()
        assert result["total"] == 19744
        assert len(result["people"]) == 2
        assert result["people"][0]["message_count"] == 5

    def test_empty_page_falls_back_to_a_real_count_instead_of_reporting_zero(self):
        with patch.object(people, "run_query", side_effect=[[], [(19744,)]]) as run_query:
            result = people.list_people(page=9999)

        assert run_query.call_count == 2
        assert result["total"] == 19744
        assert result["people"] == []


class TestGetPersonMessages:
    def test_total_comes_from_the_row_window_function(self):
        posted = datetime(2026, 7, 1, tzinfo=timezone.utc)
        rows = [(10, "mailing_list", "Subject", "Alice", posted, "http://x", "snippet", 3)]
        with patch.object(people, "run_query", return_value=rows) as run_query:
            result = people.get_person_messages(person_id=1, page=1)

        run_query.assert_called_once()
        assert result["total"] == 3
        assert result["messages"][0]["posted_at"] == posted.isoformat()

    def test_empty_page_falls_back_to_a_real_count(self):
        with patch.object(people, "run_query", side_effect=[[], [(3,)]]) as run_query:
            result = people.get_person_messages(person_id=1, page=50)

        assert run_query.call_count == 2
        assert result["total"] == 3
        assert result["messages"] == []
