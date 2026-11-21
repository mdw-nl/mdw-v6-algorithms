from v6core.orchestration import fan_out


class _FakeTaskClient:
    def __init__(self, fail_for: set[int] | None = None):
        self._next_id = 1
        self.created: list[dict] = []
        self._fail_for = fail_for or set()

    def create(self, input_: dict, organizations: list[int], name: str = "subtask", description=None) -> dict:
        if any(org_id in self._fail_for for org_id in organizations):
            raise RuntimeError("node offline")
        task_id = self._next_id
        self._next_id += 1
        self.created.append({"input_": input_, "organizations": list(organizations), "id": task_id})
        return {"id": task_id}

    def get(self, task_id: int) -> dict:
        raise AssertionError("not used in these tests")


class _FakeRunClient:
    def __init__(self, runs_by_task: dict[int, list[dict]]):
        self._runs_by_task = runs_by_task

    def from_task(self, task_id: int) -> list[dict]:
        return self._runs_by_task.get(task_id, [])


class _FakeResultClient:
    def __init__(self, results_by_id: dict[int, dict]):
        self._results_by_id = results_by_id

    def get(self, result_id: int):
        return self._results_by_id.get(result_id)


class _FakeClient:
    def __init__(self, runs_by_task=None, results_by_id=None, fail_for=None):
        self.task = _FakeTaskClient(fail_for=fail_for)
        self.run = _FakeRunClient(runs_by_task or {})
        self.result = _FakeResultClient(results_by_id or {})
        self.organization_id = 0


def _run(org_id: int, status: str, result_id: int) -> dict:
    return {"organization": {"id": org_id}, "status": status, "results": {"id": result_id}}


def test_fan_out_shared_kwargs_single_task_ok():
    client = _FakeClient(
        runs_by_task={1: [_run(1, "completed", 10), _run(2, "completed", 20)]},
        results_by_id={10: {"status": "ok", "result": {}}, 20: {"status": "ok", "result": {}}},
    )

    outcomes = fan_out(client, method="m", organizations=[1, 2], kwargs={"x": 1}, timeout_s=5)

    assert outcomes[1].status == "ok"
    assert outcomes[2].status == "ok"
    assert len(client.task.created) == 1  # one task shared across both orgs


def test_fan_out_marks_crashed_run_as_error():
    client = _FakeClient(
        runs_by_task={1: [_run(1, "completed", 10), _run(2, "crashed", 20)]},
        results_by_id={10: {"status": "ok", "result": {}}},
    )

    outcomes = fan_out(client, method="m", organizations=[1, 2], timeout_s=5)

    assert outcomes[1].status == "ok"
    assert outcomes[2].status == "error"
    assert outcomes[2].reason is not None
    assert "crashed" in outcomes[2].reason


def test_fan_out_times_out_when_no_run_ever_appears():
    client = _FakeClient(runs_by_task={})

    outcomes = fan_out(client, method="m", organizations=[3], timeout_s=0.05)

    assert outcomes[3].status == "timeout"


def test_fan_out_one_stuck_org_does_not_delay_the_others_in_the_same_task():
    # Both organizations share ONE task (kwargs are shared, see AGENTS.md §7.2): org 2
    # has no node running and its run sits in "pending" forever. Org 1's run is
    # "completed" from the very first poll. Org 1 must come back "ok" immediately --
    # not wait for (or be dragged down by) org 2's eventual timeout.
    client = _FakeClient(
        runs_by_task={1: [_run(1, "completed", 10), _run(2, "pending", 20)]},
        results_by_id={10: {"status": "ok", "result": {}}},
    )

    outcomes = fan_out(client, method="m", organizations=[1, 2], timeout_s=0.05)

    assert outcomes[1].status == "ok"
    assert outcomes[2].status == "timeout"


def test_fan_out_per_org_kwargs_creates_one_task_each():
    client = _FakeClient(
        runs_by_task={1: [_run(1, "completed", 10)], 2: [_run(2, "completed", 20)]},
        results_by_id={10: {"status": "ok"}, 20: {"status": "ok"}},
    )

    outcomes = fan_out(
        client,
        method="m",
        organizations=[1, 2],
        kwargs={"shared": True},
        per_org_kwargs={1: {"u": "a"}, 2: {"u": "b"}},
        timeout_s=5,
    )

    assert len(client.task.created) == 2
    assert outcomes[1].status == "ok"
    assert outcomes[2].status == "ok"
    merged_inputs = {tuple(t["organizations"]): t["input_"]["kwargs"] for t in client.task.created}
    assert merged_inputs[(1,)] == {"shared": True, "u": "a"}
    assert merged_inputs[(2,)] == {"shared": True, "u": "b"}


def test_fan_out_malformed_envelope_is_an_error():
    client = _FakeClient(
        runs_by_task={1: [_run(1, "completed", 10)]},
        results_by_id={10: {"not_an_envelope": True}},
    )

    outcomes = fan_out(client, method="m", organizations=[1], timeout_s=5)

    assert outcomes[1].status == "error"
    assert outcomes[1].reason is not None
    assert "Malformed" in outcomes[1].reason


def test_fan_out_task_creation_failure_is_an_error():
    client = _FakeClient(fail_for={1})

    outcomes = fan_out(client, method="m", organizations=[1], timeout_s=5)

    assert outcomes[1].status == "error"
    assert outcomes[1].reason is not None
    assert "Could not create subtask" in outcomes[1].reason
