#!/usr/bin/env python3
"""Dev network orchestration (AGENTS.md §5).

Wraps the pinned vantage6 4.x CLI (`v6 server/node/algorithm-store`) and `docker`
directly -- the scripts never call a different CLI than the one pinned in
versions.toml. Forked from the proven pattern in the sibling repo
`v6-infrastructure-sh/infrastructure/{setup,shutdown,functions}.sh` (server start,
then `docker exec ... vserver-local import` into the *running* server container so
the import always lands in the same database the server actually reads from --
`v6 dev create-demo-network`'s own one-shot import container does not reliably share
that database in this environment, which is why this re-implements that one step
instead of using `v6 dev` end to end).

Usage (also see `up.sh`/`down.sh`/`reset.sh`/`status.sh`/`push_image.sh`, which are
thin wrappers around this):
    uv run python dev-network/scripts/devnet.py up --scenario healthy
    uv run python dev-network/scripts/devnet.py down
    uv run python dev-network/scripts/devnet.py reset --scenario healthy
    uv run python dev-network/scripts/devnet.py status
    uv run python dev-network/scripts/devnet.py push-image --image NAME --tag TAG
"""

import argparse
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DEV_NETWORK_DIR = SCRIPT_DIR.parent
REPO_ROOT = DEV_NETWORK_DIR.parent
SCENARIOS_DIR = DEV_NETWORK_DIR / "scenarios"
GENERATED_DIR = DEV_NETWORK_DIR / "generated"  # gitignored, recreated by `up`
DATAVALGEN_DIR = REPO_ROOT / "datavalgen" / "generated"

SERVER_NAME = "mdw_v6_dev"
SERVER_PORT = 7601
UI_PORT = 7600
STORE_PORT = 7602
API_PATH = "/api"
REGISTRY_NAME = "mdw-v6-dev-registry"
REGISTRY_PORT = 5151

# Reachable by every container on the default Linux docker0 bridge without Docker
# Desktop (see `v6 dev create-demo-network --help`'s own advice for this case).
HOST_FROM_CONTAINERS = "http://172.17.0.1"

V6_IMAGE_REGISTRY = "ghcr.io/mdw-nl/vantage6/infrastructure"
V6_IMAGE_TAG = "4.14.0-rc8"
SERVER_IMAGE = f"{V6_IMAGE_REGISTRY}/server-lite:{V6_IMAGE_TAG}"
NODE_IMAGE = f"{V6_IMAGE_REGISTRY}/node-lite:{V6_IMAGE_TAG}"
UI_IMAGE = f"{V6_IMAGE_REGISTRY}/ui:{V6_IMAGE_TAG}"
# vantage6's own default is "infrastructure/algorithm-store:<version>"
# (vantage6.common.globals.DEFAULT_ALGO_STORE_IMAGE) -- this is the equivalent on
# MDW's mirror. As of this writing MDW has not published this image (only
# server-lite/node-lite/ui), and the upstream community image lives on
# harbor2.vantage6.ai, which this environment cannot reach (DNS fails). The store
# step below is best-effort and must never abort the rest of `up` when the image
# can't be pulled -- see `_try_start_store`.
STORE_IMAGE = f"{V6_IMAGE_REGISTRY}/algorithm-store:{V6_IMAGE_TAG}"

ADMIN_USERNAME = "dev_admin"
ADMIN_PASSWORD = "ior8ahP7ahqu3ees"  # dev-only, fake, committed on purpose


def log(message: str) -> None:
    print(f"[dev-network] {message}", flush=True)


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def load_scenario(name: str) -> dict:
    path = SCENARIOS_DIR / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))
        sys.exit(f"Unknown scenario '{name}'. Available: {available}")
    return yaml.safe_load(path.read_text())


# The config schema validates `logging` as a whole block; a trimmed-down version
# (missing `file`/`max_size`/`loggers`) fails validation, so this mirrors the proven
# shape from v6-infrastructure-sh/infrastructure/demoserver.yaml exactly.
_LOGGING_YAML = """\
logging:
  backup_count: 1
  datefmt: '%Y-%m-%d %H:%M:%S'
  file: dev-network.log
  format: '%(asctime)s - %(name)-14s - %(levelname)-8s - %(message)s'
  level: INFO
  loggers:
  - level: warning
    name: urllib3
  - level: warning
    name: sqlalchemy.engine
  max_size: 1024
  use_console: true
"""


def server_config_yaml() -> str:
    return f"""\
allow_drop_all: true
api_path: {API_PATH}
description: 'MDW v6 algorithms dev server (fake creds, dev only)'
ip: 0.0.0.0
jwt_secret_key: {uuid.uuid5(uuid.NAMESPACE_DNS, SERVER_NAME)}
{_LOGGING_YAML}\
port: '{SERVER_PORT}'
uri: sqlite:///default.sqlite
server_url: {HOST_FROM_CONTAINERS}:{SERVER_PORT}{API_PATH}
"""


def store_config_yaml() -> str:
    return f"""\
allow_drop_all: true
description: 'MDW v6 algorithms dev algorithm store (fake creds, dev only)'
ip: 0.0.0.0
{_LOGGING_YAML}\
port: '{STORE_PORT}'
uri: sqlite:///store.sqlite
root_user:
  v6_server_uri: {HOST_FROM_CONTAINERS}:{SERVER_PORT}{API_PATH}
  username: {ADMIN_USERNAME}
policies:
  algorithm_view: public
  allow_localhost: true
"""


def node_config_yaml(org: dict, profile_path: Path) -> str:
    return f"""\
api_key: {org["api_key"]}
api_path: {API_PATH}
databases:
  - label: default
    type: csv
    uri: {profile_path}
    mount_mode: ro
encryption:
  enabled: false
  private_key: ''
policies:
  allowed_algorithms: ["^localhost:{REGISTRY_PORT}/.*", "^ghcr\\\\.io/.*"]
  require_algorithm_pull: false
{_LOGGING_YAML}\
port: '{SERVER_PORT}'
server_url: {HOST_FROM_CONTAINERS}
task_dir: ./{org["name"]}/tasks
share_config: false
share_algorithm_logs: false
node_extra_hosts:
  host.docker.internal: host-gateway
"""


def entities_yaml(scenario: dict) -> str:
    lines = [
        "collaborations:",
        "- encrypted: false",
        f"  name: {scenario['collaboration']}",
        "  participants:",
    ]
    for org in scenario["organizations"]:
        lines.append(f"  - api_key: {org['api_key']}")
        lines.append(f"    name: {org['name']}")
    lines.append("  tasks: []")
    lines.append("nodes: []")
    lines.append("organizations:")
    for i, org in enumerate(scenario["organizations"]):
        name = org["name"]
        lines.append(f"- name: {name}")
        if i == 0:
            lines.append("  make_admin: true")
        lines.append(f"  address1: {name} street 1")
        lines.append("  address2: ''")
        lines.append("  country: Unknown")
        lines.append(f"  domain: {name}.local")
        lines.append("  public_key: ''")
        lines.append("  users:")
        lines.append(f"  - email: {name}-user@example.org")
        lines.append(f"    username: {name}_user")
        lines.append(f"    firstname: {name}")
        lines.append("    lastname: User")
        lines.append(f"    password: {name}-{ADMIN_PASSWORD}")
        if i == 0:
            lines.append(f"  - email: {ADMIN_USERNAME}@example.org")
            lines.append(f"    username: {ADMIN_USERNAME}")
            lines.append("    firstname: admin")
            lines.append("    lastname: robot")
            lines.append(f"    password: {ADMIN_PASSWORD}")
        lines.append("  zipcode: '0000AA'")
    return "\n".join(lines) + "\n"


def ensure_datavalgen_profiles() -> None:
    if DATAVALGEN_DIR.exists() and any(DATAVALGEN_DIR.glob("*.csv")):
        return
    log("datavalgen/generated is empty; regenerating profiles")
    run(["uv", "run", "python", "datavalgen/generate_profiles.py"], cwd=REPO_ROOT)


def find_running_server_container() -> str | None:
    result = subprocess.run(
        ["docker", "ps", "-qf", f"label=name={SERVER_NAME}", "-f", "label=vantage6-type=server"],
        capture_output=True,
        text=True,
    )
    container_id = result.stdout.strip().splitlines()
    return container_id[0] if container_id else None


def wait_for_http(url: str, timeout_s: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        probe = subprocess.run(["curl", "-sf", url], capture_output=True)
        if probe.returncode == 0:
            return True
        time.sleep(2)
    return False


def start_registry() -> None:
    result = subprocess.run(
        ["docker", "ps", "-qf", f"name=^{REGISTRY_NAME}$"], capture_output=True, text=True
    )
    if result.stdout.strip():
        log(f"registry '{REGISTRY_NAME}' already running")
        return
    subprocess.run(["docker", "rm", "-f", REGISTRY_NAME], capture_output=True)
    run(["docker", "run", "-d", "--name", REGISTRY_NAME, "-p", f"{REGISTRY_PORT}:5000", "registry:2"])


def cmd_up(args: argparse.Namespace) -> None:
    scenario = load_scenario(args.scenario)
    ensure_datavalgen_profiles()
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    start_registry()

    server_running = find_running_server_container() is not None
    if server_running:
        log(f"server '{SERVER_NAME}' already running -- up is a no-op (AGENTS.md §5)")
        return

    server_config_path = GENERATED_DIR / f"{SERVER_NAME}.yaml"
    server_config_path.write_text(server_config_yaml())
    run(
        [
            "v6",
            "server",
            "start",
            "--user",
            "--keep",
            "-c",
            str(server_config_path),
            "--name",
            SERVER_NAME,
            "--image",
            SERVER_IMAGE,
        ]
    )

    log("waiting for server health endpoint")
    if not wait_for_http(f"http://localhost:{SERVER_PORT}{API_PATH}/health"):
        sys.exit("server did not become healthy in time")

    container_id = find_running_server_container()
    if container_id is None:
        sys.exit("could not find the running server container")

    entities_path = GENERATED_DIR / "entities.generated.yaml"
    entities_path.write_text(entities_yaml(scenario))
    run(["docker", "cp", str(entities_path), f"{container_id}:/entities.yaml"])
    run(
        [
            "docker",
            "exec",
            container_id,
            "/usr/local/bin/vserver-local",
            "import",
            "--config",
            "/mnt/config.yaml",
            "/entities.yaml",
        ]
    )

    store_up = _try_start_store()

    ui_running = subprocess.run(["docker", "ps", "-qf", "name=vantage6-ui"], capture_output=True, text=True)
    if not ui_running.stdout.strip():
        subprocess.run(["docker", "rm", "-f", "vantage6-ui"], capture_output=True)
        run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                "vantage6-ui",
                "-p",
                f"{UI_PORT}:80",
                "-e",
                f"SERVER_URL=http://localhost:{SERVER_PORT}",
                "-e",
                f"API_PATH={API_PATH}",
                UI_IMAGE,
            ]
        )

    if store_up:
        link_store_to_server()
    else:
        log(
            "skipping store-to-server linking: algorithm store did not start "
            "(see the warning above). Server, UI and nodes are unaffected."
        )

    for org in scenario["organizations"]:
        if not org.get("node", False):
            log(f"organization '{org['name']}' has no node (intentionally) -- registered, not started")
            continue
        profile_path = DATAVALGEN_DIR / f"{org['profile']}.csv"
        if not profile_path.exists():
            sys.exit(f"profile '{org['profile']}' not found at {profile_path}")
        node_config_path = GENERATED_DIR / f"{SERVER_NAME}_node_{org['name']}.yaml"
        node_config_path.write_text(node_config_yaml(org, profile_path))
        run(
            [
                "v6",
                "node",
                "start",
                "--user",
                "--keep",
                "-c",
                str(node_config_path),
                "--name",
                f"{SERVER_NAME}_node_{org['name']}",
                "--image",
                NODE_IMAGE,
            ]
        )

    log(f"dev network up: scenario='{args.scenario}', server http://localhost:{SERVER_PORT}{API_PATH}")


def _try_start_store() -> bool:
    """Start the algorithm store. Returns False (never raises) if the image can't be
    pulled -- a missing store must not take down the rest of the network (the server,
    UI and nodes are independently useful without it)."""
    store_config_path = GENERATED_DIR / f"{SERVER_NAME}_store.yaml"
    store_config_path.write_text(store_config_yaml())
    try:
        run(
            [
                "v6",
                "algorithm-store",
                "start",
                "--user",
                "--keep",
                "-c",
                str(store_config_path),
                "--name",
                f"{SERVER_NAME}_store",
                "--image",
                STORE_IMAGE,
            ]
        )
    except subprocess.CalledProcessError as exc:
        log(f"WARNING: could not start the algorithm store ({exc}); continuing without it")
        return False
    log("waiting for algorithm store health endpoint")
    if not wait_for_http(f"http://localhost:{STORE_PORT}{API_PATH}/health", timeout_s=30.0):
        log("WARNING: algorithm store did not become healthy; continuing without it")
        return False
    return True


def link_store_to_server() -> None:
    from vantage6.client import Client

    client = Client("http://localhost", SERVER_PORT, API_PATH, log_level="warn")
    client.authenticate(ADMIN_USERNAME, ADMIN_PASSWORD)
    existing = client.store.list().get("data", [])
    local_store_url = f"http://localhost:{STORE_PORT}{API_PATH}"
    if local_store_url not in [s["url"] for s in existing]:
        client.store.create(
            algorithm_store_url=local_store_url,
            name="mdw-v6-dev-store",
            all_collaborations=True,
            force=True,
        )
        log("linked local algorithm store to server")
    else:
        log("local algorithm store already linked")


def cmd_down(_args: argparse.Namespace) -> None:
    subprocess.run(["docker", "rm", "-f", "vantage6-ui"], capture_output=True)
    subprocess.run(["docker", "rm", "-f", REGISTRY_NAME], capture_output=True)
    for scenario_path in SCENARIOS_DIR.glob("*.yaml"):
        scenario = yaml.safe_load(scenario_path.read_text())
        for org in scenario["organizations"]:
            subprocess.run(
                ["v6", "node", "stop", "--user", "-n", f"{SERVER_NAME}_node_{org['name']}"],
                capture_output=True,
            )
    subprocess.run(
        ["v6", "algorithm-store", "stop", "--user", "-n", f"{SERVER_NAME}_store"], capture_output=True
    )
    subprocess.run(["v6", "server", "stop", "--user", "-n", SERVER_NAME], capture_output=True)
    # Belt-and-braces: remove by label/name directly too, in case `v6 ... stop` missed
    # a container that was started with --keep from a previous, differently-shaped run.
    for name_fragment in (SERVER_NAME, f"{SERVER_NAME}_store"):
        result = subprocess.run(
            ["docker", "ps", "-aqf", f"name={name_fragment}"], capture_output=True, text=True
        )
        for container_id in result.stdout.split():
            subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
    log("dev network down")


def _remove_local_vantage6_state() -> None:
    # `cmd_down` only stops containers; `v6 server start` bind-mounts the server's
    # SQLite DB from a host directory (~/.local/share/vantage6/server/<name>), which
    # survives that. Without wiping it, `cmd_up`'s entities re-import after a reset
    # hits "UNIQUE constraint failed: organization.name" against the old data.
    home = Path.home()
    for relative in (
        f".local/share/vantage6/server/{SERVER_NAME}",
        f".cache/vantage6/server/{SERVER_NAME}",
        f".local/share/vantage6/server/{SERVER_NAME}_store",
        f".cache/vantage6/server/{SERVER_NAME}_store",
    ):
        path = home / relative
        if path.exists():
            shutil.rmtree(path)


def cmd_reset(args: argparse.Namespace) -> None:
    cmd_down(args)
    _remove_local_vantage6_state()
    if GENERATED_DIR.exists():
        shutil.rmtree(GENERATED_DIR)
    cmd_up(args)


def cmd_status(_args: argparse.Namespace) -> None:
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"], capture_output=True, text=True
    )
    relevant = [line for line in result.stdout.splitlines() if SERVER_NAME in line or REGISTRY_NAME in line]
    if not relevant:
        print("dev network is down (no containers running)")
        return
    print("Running containers:")
    for line in relevant:
        print(f"  {line}")


def cmd_push_image(args: argparse.Namespace) -> None:
    start_registry()
    local_ref = f"{args.image}:{args.tag}"
    remote_ref = f"localhost:{REGISTRY_PORT}/{args.image}:{args.tag}"
    run(["docker", "tag", local_ref, remote_ref])
    run(["docker", "push", remote_ref])
    log(f"pushed {remote_ref}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    up_parser = sub.add_parser("up")
    up_parser.add_argument("--scenario", default="healthy")
    up_parser.set_defaults(func=cmd_up)

    down_parser = sub.add_parser("down")
    down_parser.set_defaults(func=cmd_down)

    reset_parser = sub.add_parser("reset")
    reset_parser.add_argument("--scenario", default="healthy")
    reset_parser.set_defaults(func=cmd_reset)

    status_parser = sub.add_parser("status")
    status_parser.set_defaults(func=cmd_status)

    push_parser = sub.add_parser("push-image")
    push_parser.add_argument("--image", required=True)
    push_parser.add_argument("--tag", default="dev")
    push_parser.set_defaults(func=cmd_push_image)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
