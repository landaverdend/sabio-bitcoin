from unittest.mock import patch

from agents.comms import db_tools


def _run_query_returning(rows):
    return patch.object(db_tools, "run_query", return_value=rows)


class TestSearchMessagesPersonId:
    """person_id filtering expands to every row in the canonical group."""

    def test_person_id_filter_expands_to_canonical_group(self):
        with _run_query_returning([]) as run_query:
            db_tools.search_messages(person_id=539)

        sql, params = run_query.call_args.args
        assert "member_ids" in sql
        assert "person_id IN (SELECT id FROM member_ids)" in sql
        assert "person_id = %(person_id)s" not in sql
        assert params["id"] == 539

    def test_no_person_id_omits_the_group_lookup_entirely(self):
        with _run_query_returning([]) as run_query:
            db_tools.search_messages(query="taproot")

        sql, params = run_query.call_args.args
        assert "member_ids" not in sql
        assert "id" not in params

    def test_person_id_combines_with_other_filters(self):
        with _run_query_returning([]) as run_query:
            db_tools.search_messages(
                person_id=8381,
                query="segwit",
                after="2015-01-01",
            )

        sql, params = run_query.call_args.args
        assert "person_id IN (SELECT id FROM member_ids)" in sql
        assert "search_vector @@" in sql
        assert "posted_at >=" in sql
        assert params["id"] == 8381
        assert params["q"] == "segwit"
        assert params["after"] == "2015-01-01"
