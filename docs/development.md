# Development

This project enforces a strict "full defense" CI/CD pipeline. All code must pass comprehensive unit tests, static analysis, and licensing checks before being merged.

To install the package with all development dependencies, see
[Installation](tools/validator.md#installation).

## Unit tests (pytest)

Validate the core logic of the Python executable using `pytest`. The test suite uses mock schemas located in `tests/data/`.

```bash
pytest
```

## Code quality (Ruff)

The codebase uses `Ruff` to enforce strict formatting, linting, and Google-style docstrings.

```bash
ruff format .
ruff check .
```

## Meta-schema validation

The GA4GH meta-schemas themselves must strictly conform to the JSON Schema Draft 2020-12 specification. We validate this using `check-jsonschema`.

```bash
check-jsonschema --check-metaschema schemas/ga4gh-io-profile.schema.json
check-jsonschema --check-metaschema schemas/vocabularies/ui-widgets.schema.json
```

## License compliance (REUSE)

All files must have clear copyright and licensing information compliant with the [REUSE specification](https://reuse.software/). The primary codebase is Apache-2.0, while documentation is CC-BY-4.0.

```bash
reuse lint
```

## Documentation linting

Markdown files are linted to ensure consistent structure and catch broken links.

```bash
npx markdownlint-cli "**/*.md" --ignore "node_modules"
```

## Documentation

The documentation is built with [MkDocs](https://www.mkdocs.org/) and
[Material for MkDocs](https://squidfunk.github.io/mkdocs-material/), and
published on [Read the Docs](https://ga4gh-io-schema.readthedocs.io/), which
also builds a preview for each pull request. Its sources are in `docs/`, the
navigation in `mkdocs.yml`; the [Python API](tools/validator.md#python-api)
is generated from the docstrings with
[mkdocstrings](https://mkdocstrings.github.io/). Install the `docs` extra
and build the site as CI does, which fails on any warning (e.g., broken
links or anchors):

```bash
pip install -e ".[docs]"
mkdocs build --strict
```

`mkdocs serve` serves the site at <http://127.0.0.1:8000/> and rebuilds it on
changes. The home page includes the synopsis of `README.md` (between the
`--8<-- [start:synopsis]` and `--8<-- [end:synopsis]` markers), and
[Examples](specification/examples.md) include the example schemas of
`tests/data/`; the build fails if they are missing. Link to files of the
repository with their URL on GitHub, as MkDocs can't check links outside
`docs/`.
