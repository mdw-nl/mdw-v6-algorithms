"""Structural types for `AlgorithmClient`-like objects.

`vantage6.algorithm.client.AlgorithmClient` and `vantage6.algorithm.tools.mock_client.
MockAlgorithmClient` are unrelated classes (the mock doesn't subclass the real one), and
our own test doubles are unrelated to both -- all three are accepted by duck typing
throughout this package. A `Protocol` lets `ty` check that duck typing structurally
instead of either over-constraining to one concrete class or giving up with `object`.
"""

from typing import Any, Protocol

from vantage6.algorithm.tools.mock_client import MockAlgorithmClient


class TaskClient(Protocol):
    # `description` is `str` (not `str | None`), matching the real
    # `AlgorithmClient.Task.create`'s annotation -- which is itself inaccurate (its
    # default is `None`) but a Protocol's parameter types must be contravariant, so
    # matching the (wrong) upstream annotation is what makes this structurally
    # compatible. Callers in this package never actually pass `None` here (see
    # `fan_out`, which resolves it to `name` first).
    def create(
        self,
        input_: dict,
        organizations: list[int],
        name: str = ...,
        description: str = ...,
    ) -> dict: ...

    def get(self, task_id: int) -> dict: ...


class RunClient(Protocol):
    def from_task(self, task_id: int) -> list[dict]: ...


class ResultClient(Protocol):
    def from_task(self, task_id: int) -> list[Any]: ...


class AlgorithmClientLike(Protocol):
    # Declared as read-only properties (not plain attribute annotations) so a
    # concrete client's more specific attribute type (e.g. a test double's own
    # `ResultClient` implementation) is accepted covariantly -- a plain attribute
    # annotation is invariant and would reject any concrete type but the exact one.
    @property
    def organization_id(self) -> int: ...

    @property
    def task(self) -> TaskClient: ...

    @property
    def run(self) -> RunClient: ...

    @property
    def result(self) -> ResultClient: ...


# `MockAlgorithmClient.Task.create` is annotated `-> int` upstream even though it
# actually returns a dict (a type-hint bug in vantage6-algorithm-tools==4.14.0, not
# something we can fix) -- so it fails `AlgorithmClientLike` structurally despite being
# a real, supported client throughout this package. Every function that accepts "a
# client, real or mocked" should take this union rather than the bare protocol.
AnyAlgorithmClient = AlgorithmClientLike | MockAlgorithmClient
