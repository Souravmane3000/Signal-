from io import StringIO
from unittest.mock import patch

from agent.nodes.run_metrics_writer import run_metrics_writer


def _state(**overrides):
    base = {
        "run_id": "test_run_001",
        "graph_version": "1.0",
        "sources_queried": ["tavily", "yc"],
        "findings_retrieved": 20,
        "findings_dropped_freshness": 3,
        "findings_dropped_scope": 2,
        "findings_dropped_dedup": 1,
        "new_findings": [{}, {}],
        "tokens_used": 5000,
        "estimated_cost_usd": 0.05,
        "source_failures": {
            "tavily": False,
            "yc": True,
            "hn": False,
            "rss": False,
        },
    }
    base.update(overrides)
    return base


def test_returns_empty_dict():
    with patch("sys.stdout", new_callable=StringIO):
        result = run_metrics_writer(_state())
    assert result == {}


def test_prints_all_required_metrics():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(_state())
    output = buf.getvalue()
    required = [
        "run_id",
        "graph_version",
        "sources_queried",
        "findings_retrieved",
        "findings_dropped_freshness",
        "findings_dropped_scope",
        "findings_dropped_dedup",
        "findings_in_briefing",
        "tokens_used",
        "estimated_cost_usd",
        "source_health",
    ]
    for key in required:
        assert f"{key}:" in output, f"missing metric line: {key}"


def test_graph_version_and_source_health_visible():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(_state())
    output = buf.getvalue()
    assert "graph_version: 1.0" in output
    assert "source_health:" in output


def test_drop_counters_printed_separately():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(_state())
    output = buf.getvalue()
    assert "findings_dropped_freshness: 3" in output
    assert "findings_dropped_scope: 2" in output
    assert "findings_dropped_dedup: 1" in output
    # Must not combine into a single aggregate line
    assert "findings_dropped:" not in output


def test_warning_for_failed_sources():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(_state())
    output = buf.getvalue()
    assert "WARNING: yc failed this run" in output
    assert "WARNING: tavily failed this run" not in output
    assert "WARNING: hn failed this run" not in output
    assert "WARNING: rss failed this run" not in output


def test_multiple_failed_sources_each_get_warning():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(
            _state(
                source_failures={
                    "tavily": True,
                    "yc": True,
                    "hn": False,
                    "rss": True,
                }
            )
        )
    output = buf.getvalue()
    assert "WARNING: tavily failed this run" in output
    assert "WARNING: yc failed this run" in output
    assert "WARNING: rss failed this run" in output
    assert "WARNING: hn failed this run" not in output


def test_findings_in_briefing_from_new_findings_length():
    buf = StringIO()
    with patch("sys.stdout", buf):
        run_metrics_writer(_state(new_findings=[{}, {}, {}]))
    assert "findings_in_briefing: 3" in buf.getvalue()


def test_does_not_modify_state():
    state = _state()
    original = dict(state)
    with patch("sys.stdout", new_callable=StringIO):
        run_metrics_writer(state)
    assert state == original


if __name__ == "__main__":
    test_returns_empty_dict()
    test_prints_all_required_metrics()
    test_graph_version_and_source_health_visible()
    test_drop_counters_printed_separately()
    test_warning_for_failed_sources()
    test_multiple_failed_sources_each_get_warning()
    test_findings_in_briefing_from_new_findings_length()
    test_does_not_modify_state()
    print("Run metrics writer test passed.")
