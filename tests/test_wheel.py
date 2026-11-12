# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""End-to-end test: build the wheel, install it and run the CLI.

The test needs network access to install the build backend and the
runtime dependencies into a fresh virtual environment.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((REPO_ROOT / "tests" / "data").glob("example_*.schema.json"))


@pytest.fixture(scope="module")
def installed_cli(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel and install it into a fresh virtual environment.

    Args:
        tmp_path_factory: Pytest fixture for module-scoped temporary directories.

    Returns:
        Path to the installed command-line entry point.
    """
    work_dir = tmp_path_factory.mktemp("wheel")
    dist_dir = work_dir / "dist"
    env_dir = work_dir / "venv"
    venv.create(env_dir, with_pip=True)
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", dist_dir, REPO_ROOT],
        check=True,
        capture_output=True,
    )
    wheels = list(dist_dir.glob("*.whl"))
    assert len(wheels) == 1
    subprocess.run(
        [bin_dir / "python", "-m", "pip", "install", wheels[0]],
        check=True,
        capture_output=True,
    )
    return bin_dir / "ga4gh-io-schema-validator"


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
        [installed_cli, example],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "complies with the GA4GH IO Profile" in result.stdout
