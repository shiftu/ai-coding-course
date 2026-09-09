from weekly_report.summarize import (collect_topics, count_by_author,
                                     count_words, top_contributors)
from weekly_report.fetch import fetch_messages

MSGS = fetch_messages("demo-chat")


def test_count_by_author():
    counts = count_by_author(MSGS)
    assert counts["Alice"] == 5
    assert counts["Erin"] == 1


def test_top_contributors_is_most_active_first():
    counts = count_by_author(MSGS)
    assert top_contributors(counts) == ["Alice", "Bob", "Carol"]


def test_collect_topics():
    topics = collect_topics(MSGS)
    assert topics["发布"] == 3


def test_count_words_is_positive():
    assert all(v > 0 for v in count_words(MSGS).values())
