from v6run.reporting import print_summary, write_summary_md

PARTIAL_ENVELOPE = {
    "status": "partial",
    "algorithm": {"name": "descriptive_statistics", "version": "0.1.0", "v6core_version": "0.1.0"},
    "participation": [
        {"organization": "alpha", "status": "included"},
        {"organization": "beta", "status": "failed", "reason": "BELOW_MIN_ROWS"},
    ],
    "result": {"columns": {"age": {"mean": 42.0}}},
    "warnings": ["beta: column:site: missing"],
    "errors": [],
    "privacy": {"thresholds": {"min_cell_count": 5}},
}


def test_print_summary_mentions_partial_status_and_warnings(capsys):
    print_summary(PARTIAL_ENVELOPE)
    out = capsys.readouterr().out

    assert "PARTIAL" in out
    assert "beta" in out
    assert "BELOW_MIN_ROWS" in out
    assert "missing" in out


def test_write_summary_md_includes_participation_table(tmp_path):
    path = tmp_path / "summary.md"
    write_summary_md(PARTIAL_ENVELOPE, path)
    content = path.read_text()

    assert "PARTIAL" in content
    assert "| alpha | included |  |" in content
    assert "| beta | failed | BELOW_MIN_ROWS |" in content


def test_ok_status_does_not_look_like_an_error(capsys):
    ok_envelope = {**PARTIAL_ENVELOPE, "status": "ok", "warnings": [], "errors": []}
    print_summary(ok_envelope)
    out = capsys.readouterr().out

    assert "=== Result: OK ===" in out
