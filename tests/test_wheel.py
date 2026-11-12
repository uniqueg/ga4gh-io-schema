# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test: build the wheel, install it and run the CLI.

The tests need network access to install the build backend and the
runtime dependencies into a fresh virtual environment. Deselect them with
``pytest -m "not wheel"`` when offline.
"""

import json
import os
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.wheel

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "tests" / "data"
EXAMPLES = sorted(DATA_DIR.glob("example_*.schema.json"))
SCHEMAS_DIR = REPO_ROOT / "schemas"
#: Every schema of the repository, as the wheel must ship it.
PACKAGED_SCHEMAS = sorted(
    f"ga4gh_io_schema/schemas/{path.relative_to(SCHEMAS_DIR).as_posix()}"
    for path in SCHEMAS_DIR.rglob("*.json")
)


def _run(command: list[str | Path], **kwargs: object) -> None:
    """Run a command and fail the test with its output if it fails.

    Args:
        command: Command and arguments to run.
        **kwargs: Further keyword arguments for :func:`subprocess.run`.
    """
    result = subprocess.run(
        command, capture_output=True, text=True, check=False, **kwargs
    )
    if result.returncode != 0:
        pytest.fail(f"{command} failed:\n{result.stdout}\n{result.stderr}")


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel of the package.

    Args:
        tmp_path_factory: Pytest fixture for module-scoped temporary directories.

    Returns:
        Path to the built wheel.
    """
    dist_dir = tmp_path_factory.mktemp("dist")
    _run([sys.executable, "-m", "build", "--wheel", "--outdir", dist_dir, REPO_ROOT])
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


@pytest.fixture(scope="module")
def installed_cli(wheel: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Install the wheel into a fresh virtual environment.

    Args:
        wheel: Path to the built wheel.
        tmp_path_factory: Pytest fixture for module-scoped temporary directories.

    Returns:
        Path to the installed command-line entry point.
    """
    env_dir = tmp_path_factory.mktemp("venv")
    venv.create(env_dir, with_pip=True)
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    _run([bin_dir / "python", "-m", "pip", "install", wheel])
    return bin_dir / "ga4gh-io-schema"


def test_wheel_ships_schemas(wheel: Path) -> None:
    """Test that the wheel contains the meta-schema and its vocabularies.

    Args:
        wheel: Path to the built wheel.
    """
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()

    for name in PACKAGED_SCHEMAS:
        assert name in names


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda path: path.name)
def test_installed_cli_validates_example(
    installed_cli: Path, example: Path, tmp_path: Path
) -> None:
    """Test that the installed CLI validates an example outside the checkout.

    Args:
        installed_cli: Path to the installed command-line entry point.
        example: Example schema to validate.
        tmp_path: Pytest fixture providing a working directory outside the repo.
    """
    result = subprocess.run(
        [installed_cli, "validate", example],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "complies with the GA4GH IO Profile" in result.stdout


def test_installed_cli_checks_formats(installed_cli: Path, tmp_path: Path) -> None:
    """Test that the installed CLI enforces formats (``format-nongpl`` extra).

    Args:
        installed_cli: Path to the installed command-line entry point.
        tmp_path: Pytest fixture providing a working directory outside the repo.
    """
    schema = json.loads((DATA_DIR / "valid.schema.json").read_text(encoding="utf-8"))
    schema["$id"] = "http://[invalid"
    path = tmp_path / "bad-id.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")

    result = subprocess.run(
        [installed_cli, "validate", path],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "is not a 'uri-reference'" in result.stderr


def test_installed_cli_checks_nested_vocabulary(
    installed_cli: Path, tmp_path: Path
) -> None:
    """Test that the installed CLI applies the vocabularies to nested schemas.

    Args:
        installed_cli: Path to the installed command-line entry point.
        tmp_path: Pytest fixture providing a working directory outside the repo.
    """
    result = subprocess.run(
        [
            installed_cli,
            "validate",
            DATA_DIR / "invalid" / "tabular-schema-nested.schema.json",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "'no' is not of type 'boolean'" in result.stderr
