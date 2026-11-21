import pytest

from v6core.participation import (
    ParticipationError,
    apply_min_floor,
    check_quorum,
    select_organizations,
)

ORGS = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}, {"id": 3, "name": "gamma"}]


def test_select_organizations_none_returns_all():
    assert select_organizations(ORGS, None) == ORGS


def test_select_organizations_filters_by_name():
    result = select_organizations(ORGS, ["beta"])
    assert [o["id"] for o in result] == [2]


def test_select_organizations_empty_list_raises():
    with pytest.raises(ParticipationError) as exc_info:
        select_organizations(ORGS, [])
    assert exc_info.value.code == "INVALID_PARAM"


def test_select_organizations_unknown_name_raises():
    with pytest.raises(ParticipationError) as exc_info:
        select_organizations(ORGS, ["delta"])
    assert "delta" in exc_info.value.message


def test_apply_min_floor_splits_by_threshold():
    counts = {1: 10, 2: 2, 3: None}
    qualifying, excluded = apply_min_floor(counts, minimum=5, reason="BELOW_MIN_ROWS")
    assert qualifying == [1]
    assert excluded == {2: "BELOW_MIN_ROWS", 3: "BELOW_MIN_ROWS"}


def test_check_quorum_passes():
    check_quorum(2, min_organizations=2)  # no raise


def test_check_quorum_raises_when_not_met():
    with pytest.raises(ParticipationError) as exc_info:
        check_quorum(1, min_organizations=2)
    assert exc_info.value.code == "QUORUM_NOT_MET"
