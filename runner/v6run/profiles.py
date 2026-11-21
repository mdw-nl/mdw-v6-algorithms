"""Server connection profiles (AGENTS.md §9.5: `profile: dev` = the local dev network).

Credentials never go in a study file or in code (AGENTS.md §9.5), following grimoire's
secrets policy (company/security.md: person-bound passwords live in a password manager,
never committed) -- dev-network fake credentials excepted, and even those are read from
the environment here, not hard-coded, so the same lookup path works for a real profile.
Set real values from a file OUTSIDE this repo (e.g. `~/.v6run-<profile>.env`, `chmod 600`,
`source`d before running `v6run`) -- never inside the project directory, where an editor
or tooling watching the tree could surface a secret in plaintext.
"""

import os
from dataclasses import dataclass

_DEV_DEFAULTS = {
    # Matches dev-network/README.md's committed, fake dev_admin account and the server
    # port devnet.py actually starts on -- dev-only and fine to default to since none of
    # this is ever reused anywhere else.
    "SERVER_URL": "http://localhost",
    "PORT": "7601",
    "API_PATH": "/api",
    "USERNAME": "dev_admin",
    "PASSWORD": "ior8ahP7ahqu3ees",
    "DATABASE_LABEL": "default",
}


class UnknownProfileError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ServerProfile:
    server_url: str
    port: int
    api_path: str
    username: str
    password: str
    database_label: str = "default"
    # Path to the organization's EXISTING node encryption private key (the same file its
    # node's own config.yaml points at), required only for a collaboration that enforces
    # encryption. None means "connect unencrypted" -- fine for the dev network, fatal
    # against a real encryption-enforcing collaboration.
    private_key_path: str | None = None


def resolve_profile(name: str) -> ServerProfile:
    """Resolve `name` to connection details, sourced from `V6RUN_<NAME>_*` env vars.

    The 'dev' profile has built-in fallback defaults pointing at the local dev network
    (AGENTS.md §5) -- safe only because those credentials are never real. Any other
    profile name has no defaults at all: every required variable must be set explicitly
    (e.g. `V6RUN_PROD_SERVER_URL`, `V6RUN_PROD_USERNAME`, ...), so connecting to a real
    network is always an explicit, visible configuration step, never an accidental
    fallback.
    """
    prefix = f"V6RUN_{name.upper()}_"
    defaults = _DEV_DEFAULTS if name == "dev" else {}

    def _optional(key: str) -> str | None:
        return os.environ.get(prefix + key, defaults.get(key))

    def _required(key: str) -> str:
        value = _optional(key)
        if not value:
            raise UnknownProfileError(
                f"Missing required environment variable '{prefix}{key}' for profile '{name}'. "
                "Set it from a file outside this repo (never inside the project directory) "
                "before running -- see runner/README.md."
            )
        return value

    return ServerProfile(
        server_url=_required("SERVER_URL"),
        port=int(_required("PORT")),
        api_path=_optional("API_PATH") or "/api",
        username=_required("USERNAME"),
        password=_required("PASSWORD"),
        database_label=_optional("DATABASE_LABEL") or "default",
        private_key_path=_optional("PRIVATE_KEY_PATH"),
    )
