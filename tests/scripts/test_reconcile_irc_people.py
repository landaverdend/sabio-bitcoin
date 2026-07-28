from unittest.mock import MagicMock

from scripts import reconcile_irc_people


def test_find_candidates_uses_curated_aliases_and_unique_exact_github_roots():
    roots = reconcile_irc_people._github_roots(
        [
            ("glozow", 538),
            ("glozow", 538),
            ("michaelfolkson", 953),
            ("ambiguous", 50),
            ("ambiguous", 51),
        ]
    )
    sources = [
        (538, "glozow", 100),
        (10, "gzhao408", 20),
        (11, "michaelfolkson", 30),
        (12, "ambiguous", 40),
        (13, "unknown", 50),
    ]

    candidates, stats = reconcile_irc_people._find_candidates(sources, roots)

    assert [(c.source_id, c.target_id, c.reason) for c in candidates] == [
        (10, 538, "curated_alias"),
        (11, 953, "exact_github_username"),
    ]
    assert stats["events_reconciled"] == 50
    assert stats["already_canonical_root"] == 1
    assert stats["ambiguous_github_match"] == 1
    assert stats["without_github_match"] == 1


def test_apply_candidate_links_source_and_flattens_existing_children():
    cur = MagicMock()
    cur.fetchone.side_effect = [(None,), (None,)]
    cur.rowcount = 1
    candidate = reconcile_irc_people.Candidate(
        source_id=10,
        irc_nick="michaelfolkson",
        target_id=953,
        target_github_username="michaelfolkson",
        reason="exact_github_username",
        event_count=30,
    )

    linked = reconcile_irc_people._apply_candidate(cur, candidate)

    assert linked is True
    assert cur.execute.call_count == 4
    assert cur.execute.call_args.args[1] == {
        "source_id": 10,
        "target_id": 953,
    }
