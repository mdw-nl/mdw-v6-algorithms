"""Server connection profiles (AGENTS.md §9.5: `profile: dev` = the local dev network).

Credentials never go in a study file or in code (AGENTS.md §9.5) -- dev-network fake
credentials excepted, and even those are read from the environment here, not hard-coded,
so the same lookup path works for a real profile later.
"""

import os
from dataclasses import dataclass


class UnknownProfileError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ServerProfile:
    server_url: str
    port: int
    api_path: str
    username: str
    password: str


def resolve_profile(name: str) -> ServerProfile:
    """Resolve `name` to connection details.

    The 'dev' profile points at the local dev network (AGENTS.md §5) by default,
    overridable with `V6RUN_SERVER_URL`/`V6RUN_PORT`/`V6RUN_API_PATH`. Credentials
    always come from `V6RUN_USERNAME`/`V6RUN_PASSWORD` -- for 'dev' this defaults to
    the dev network's well-known, fake `dev_admin` account (see `dev-network/README.md`),
    which is fine to default to only because those credentials are never real.
    """
    if name != "dev":
        raise UnknownProfileError(
            f"Unknown profile '{name}'. Only 'dev' is defined so far; add new profiles to "
            f"v6run.profiles.resolve_profile when a real server/collaboration profile is needed."
        )

    # Matches dev-network/README.md's committed, fake dev_admin credentials and the
    # server port devnet.py actually starts on -- dev-only and fine to default to
    # since none of this is ever reused anywhere else.
    username = os.environ.get("V6RUN_USERNAME", "dev_admin")
    password = os.environ.get("V6RUN_PASSWORD", "ior8ahP7ahqu3ees")
    server_url = os.environ.get("V6RUN_SERVER_URL", "http://localhost")
    port = int(os.environ.get("V6RUN_PORT", "7601"))
    api_path = os.environ.get("V6RUN_API_PATH", "/api")

    return ServerProfile(
        server_url=server_url, port=port, api_path=api_path, username=username, password=password
    )
