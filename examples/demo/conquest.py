# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Run the demo workflow on Conquest, a GA4GH WES server.

Conquest runs workflows from a GitHub repository at a commit, not from TRS:
a run request names the repository as ``workflow_url`` and the commit and
the main workflow file in ``workflow_engine_parameters``. ``ga4gh-io-schema
wes-params`` stays server-neutral, so this script adds them.

Subcommands:

- ``request``: add Conquest's engine parameters to a run request from
  ``ga4gh-io-schema wes-params --request``;
- ``submit``: send a run request (``POST /runs``) and print the run ID;
- ``wait``: wait until a run has ended and print its ``RunLog``;
- ``run``: all of it, from the schema and the input values to the
  normalised outputs (``--dry-run`` prints the request only).

The base URL of the WES API is, e.g., ``https://conquest.example.org/ga4gh/wes/v1``.
An access token, if the server needs one, is read from the environment
variable ``WES_TOKEN``.
"""

import argparse
import json
import sys
import time
import urllib.parse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from demo_http import HTTPError, request_json
from register import DEFAULT_REPOSITORY, check_repository, check_revision

from ga4gh_io_schema.outputs import NormalisationError, normalise_outputs
from ga4gh_io_schema.wes import TranslationError, build_run_request

#: Directory of the demo.
DEMO_DIR = Path(__file__).resolve().parent
#: Path of the main workflow file in the repository.
DEFAULT_MAIN_WORKFLOW_PATH = "examples/demo/demo.wdl"
#: URI schemes of input files that Conquest stages.
CONQUEST_SCHEMES = ("https", "s3")
#: Name of the environment variable with the access token.
TOKEN_ENV = "WES_TOKEN"
#: States of WES runs that don't change any more.
FINAL_STATES = frozenset(
    {"COMPLETE", "EXECUTOR_ERROR", "SYSTEM_ERROR", "CANCELED", "PREEMPTED"}
)


def add_engine_parameters(
    request: dict[str, Any],
    revision: str,
    repository: str = DEFAULT_REPOSITORY,
    main_workflow_path: str = DEFAULT_MAIN_WORKFLOW_PATH,
) -> dict[str, Any]:
    """Turn a WES run request into one that Conquest accepts.

    Args:
        request: The run request, e.g. from ``wes-params --request``.
        revision: Full commit SHA of the repository to run.
        repository: Root URL of the GitHub repository.
        main_workflow_path: Path of the main workflow file in the repository.

    Returns:
        A copy of the request, with ``workflow_url`` set to the repository
        and ``workflow_engine_parameters`` to the revision and the path.

    Raises:
        ValueError: If the revision or the repository is malformed.
    """
    check_revision(revision)
    check_repository(repository)
    return {
        **request,
        "workflow_url": repository,
        "workflow_engine_parameters": {
            "revision": revision,
            "main_workflow_path": main_workflow_path,
        },
    }


def submit(wes_url: str, request: dict[str, Any]) -> str:
    """Submit a run request.

    Args:
        wes_url: Base URL of the WES API.
        request: The run request.

    Returns:
        The ID of the run.

    Raises:
        HTTPError: If the request fails or the response has no run ID.
    """
    response = request_json("POST", f"{wes_url.rstrip('/')}/runs", request, TOKEN_ENV)
    if not isinstance(response, dict) or not isinstance(response.get("run_id"), str):
        raise HTTPError("The response of POST /runs has no run_id")
    return response["run_id"]


def wait(
    wes_url: str,
    run_id: str,
    interval: float = 10.0,
    timeout: float = 3600.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Wait until a run has ended, and return its ``RunLog``.

    Args:
        wes_url: Base URL of the WES API.
        run_id: The ID of the run.
        interval: Seconds between two checks of the state.
        timeout: Seconds to wait at most.
        sleep: Function that waits (for tests).
        clock: Monotonic clock in seconds (for tests).

    Returns:
        The ``RunLog`` of the run (``GET /runs/{run_id}``).

    Raises:
        HTTPError: If a request fails.
        TimeoutError: If the run hasn't ended in time.
    """
    base = f"{wes_url.rstrip('/')}/runs/{urllib.parse.quote(run_id, safe='')}"
    deadline = clock() + timeout
    while True:
        status = request_json("GET", f"{base}/status", token_env=TOKEN_ENV)
        state = status.get("state") if isinstance(status, dict) else None
        if state in FINAL_STATES:
            break
        if clock() + interval > deadline:
            raise TimeoutError(f"Run {run_id} hasn't ended (state {state})")
        print(f"Run {run_id}: {state}", file=sys.stderr)
        sleep(interval)
    run_log = request_json("GET", base, token_env=TOKEN_ENV)
    if not isinstance(run_log, dict):
        raise HTTPError(f"The RunLog of run {run_id} isn't a JSON object")
    return run_log


def _load_json(path: str) -> Any:
    """Read a JSON file, or standard input for ``-``."""
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_json(value: Any) -> None:
    """Print a JSON value, indented."""
    print(json.dumps(value, indent=2))


def _cmd_request(args: argparse.Namespace) -> int:
    """Add Conquest's engine parameters to a run request."""
    request = _load_json(args.request)
    _print_json(
        add_engine_parameters(
            request, args.revision, args.repository, args.main_workflow_path
        )
    )
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    """Submit a run request and print the run ID."""
    print(submit(args.wes_url, _load_json(args.request)))
    return 0


def _cmd_wait(args: argparse.Namespace) -> int:
    """Wait until a run has ended and print its RunLog."""
    _print_json(wait(args.wes_url, args.run_id, args.interval, args.timeout))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Build, submit and wait for a run, then normalise its outputs."""
    schema = _load_json(args.schema)
    values = _load_json(args.values)
    request = build_run_request(
        schema,
        values,
        workflow_url=args.repository,
        allowed_schemes=CONQUEST_SCHEMES,
    )
    request = add_engine_parameters(
        request, args.revision, args.repository, args.main_workflow_path
    )
    if args.dry_run:
        _print_json(request)
        return 0
    if not args.wes_url:
        raise ValueError("--wes-url is required unless --dry-run is given")
    run_id = submit(args.wes_url, request)
    print(f"Run {run_id} submitted", file=sys.stderr)
    run_log = wait(args.wes_url, run_id, args.interval, args.timeout)
    _print_json(normalise_outputs(schema, run_log).to_json())
    return 0


def _parser() -> argparse.ArgumentParser:
    """Build the parser of the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    def engine_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--revision",
            required=True,
            help="full commit SHA of the repository that contains the demo",
        )
        sub.add_argument(
            "--repository",
            default=DEFAULT_REPOSITORY,
            help=f"GitHub repository with the demo (default: {DEFAULT_REPOSITORY})",
        )
        sub.add_argument(
            "--main-workflow-path",
            default=DEFAULT_MAIN_WORKFLOW_PATH,
            help=f"main workflow file (default: {DEFAULT_MAIN_WORKFLOW_PATH})",
        )

    def wait_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument(
            "--interval", type=float, default=10.0, help="seconds between checks"
        )
        sub.add_argument(
            "--timeout", type=float, default=3600.0, help="seconds to wait at most"
        )

    request = commands.add_parser("request", help=_cmd_request.__doc__)
    request.add_argument("request", help="run request (JSON file, or - for stdin)")
    engine_options(request)
    request.set_defaults(func=_cmd_request)

    submit_cmd = commands.add_parser("submit", help=_cmd_submit.__doc__)
    submit_cmd.add_argument("request", help="run request (JSON file, or - for stdin)")
    submit_cmd.add_argument("--wes-url", required=True, help="base URL of the WES API")
    submit_cmd.set_defaults(func=_cmd_submit)

    wait_cmd = commands.add_parser("wait", help=_cmd_wait.__doc__)
    wait_cmd.add_argument("run_id", help="ID of the run")
    wait_cmd.add_argument("--wes-url", required=True, help="base URL of the WES API")
    wait_options(wait_cmd)
    wait_cmd.set_defaults(func=_cmd_wait)

    run = commands.add_parser("run", help=_cmd_run.__doc__)
    run.add_argument(
        "--schema",
        default=str(DEMO_DIR / "ga4gh-io.schema.json"),
        help="I/O Schema (default: the demo's)",
    )
    run.add_argument(
        "--values",
        default=str(DEMO_DIR / "values.json"),
        help="input values (default: the demo's values.json)",
    )
    run.add_argument("--wes-url", help="base URL of the WES API")
    run.add_argument(
        "--dry-run", action="store_true", help="print the run request only"
    )
    engine_options(run)
    wait_options(run)
    run.set_defaults(func=_cmd_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a subcommand.

    Args:
        argv: Command-line arguments, without the program name.

    Returns:
        The exit status: 0 on success, 1 on errors (invalid arguments or
        values, a failed request, a run that hasn't ended in time).
    """
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        HTTPError,
        NormalisationError,
        OSError,
        TimeoutError,
        TranslationError,
        ValueError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
