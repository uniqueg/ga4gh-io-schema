# Development

This project enforces a strict "full defense" CI/CD pipeline. All code must pass comprehensive unit tests, static analysis, and licensing checks before being merged.

To install the package with all development dependencies, see
[Installation](tools/validator.md#installation).

## Unit tests (pytest)

Validate the core logic of the Python executable using `pytest`. The tests use the example schemas in `tests/data/` and the schema
documents of the [conformance suite](specification/conformance.md#conformance-suite)
in `tests/conformance/`.

```bash
pytest
```

`pytest` measures coverage of the package (with branches) and fails below
100%. The CLI tests (`tests/test_cli.py`) run the command-line tool on the
examples and the valid cases of the suite, and on one deliberately bad
schema per rule of the meta-schema in
`tests/conformance/schema-documents/invalid/`, and check the exit code and
the error message of each; a new rule needs a new bad schema and its
expected message. `tests/test_conformance.py` is the runner of the
conformance suite for this package: it checks every case against the
Python API, without error messages, as other implementations do.
`tests/test_cli_framework.py` tests the shared conventions of all
subcommands (standard input, `--output`, `--json`, exit codes) and the
subcommand registry.

`tests/test_wheel.py` builds the wheel, installs it into a fresh virtual
environment and runs the command-line tool on the examples. It needs network
access to install the build backend and the dependencies; deselect it with
`pytest -m "not wheel"` when offline. CI runs the tests on every supported
Python version, from the lowest to the newest. The supported versions are set
in `requires-python` and the classifiers of `pyproject.toml`, ruff's
`target-version` and the test matrix of `.github/workflows/ci.yml`; change
them together.

## Schema versions

The `$id`s of the schemas in `schemas/`, and the `$schema` of the examples in
`tests/data/`, of the cases in `tests/conformance/` and of the snippet in the meta-schema documentation, name the
release tag of the profile (e.g., `v0.3.0`). For a new release, change the tag
in all of them at once (the tests check that they agree), and push the tag so
that the URLs resolve.

## Adding keywords

Keywords live in one vocabulary file per keyword group in
`schemas/vocabularies/`. To add a keyword or a group:

1. Add the keyword to the `properties` of its vocabulary file, or create a new
   file (with a versioned `$id`, like the others) and add a `$ref` to it to the
   `allOf` of `$defs/node` in `schemas/ga4gh-io-profile.schema.json`.
   A keyword whose value is a schema (like `x-ga4gh-tabular-schema`) uses
   `"$dynamicRef": "#meta"`, and its vocabulary file declares
   `"$dynamicAnchor": "meta"` at its root, so that the nested schema is
   checked by all rules of the profile (see `vocabularies/file.schema.json`).
2. Add one bad schema per new rule to
   `tests/conformance/schema-documents/invalid/` and its expected message
   to `INVALID` in `tests/test_cli.py`; for a schema-valued keyword,
   include a bad schema nested in it.
3. Document the keyword in `docs/specification/keywords.md` and in the table
   in `docs/specification/meta-schema.md`.

The wheel ships every file in `schemas/`, and the tests check that it does.

## Adding subcommands

Each subcommand of `ga4gh-io-schema` is a `Command` (see
`src/ga4gh_io_schema/cli/base.py`) in a module of
`src/ga4gh_io_schema/cli/commands/`; the dispatcher imports every module
there, so a new subcommand needs no change elsewhere:

1. Subclass `Command`: set `name` and `help`, add the arguments in
   `configure()`, and return a `CommandResult` from `run()`: the text
   result and, optionally, the data that `--json` writes (without data,
   `--json` writes `{"output": <text>}`). On failure, raise a `CliError`
   with an `ErrorKind`, which sets the label and the exit status. Read input
   with `read_text()` or `read_json()`, which accept `-` for standard input.
2. Register it at the end of the module: `ROOT.register(MyCommand())`, or, in
   a group, `ROOT.group("convert", help="...").register(MyCommand())`.
3. Test it through `main()` of `ga4gh_io_schema.cli`, with 100% coverage.
   Tests of the framework build their own `CommandGroup` and pass it as
   `main(argv, root=group)`, so that they don't change `ROOT`.

A new kind of error or exit status goes into `ErrorKind` and `ERROR_KINDS`,
or `ExitCode` and `EXIT_STATUS`, of `base.py` and into
`docs/tools/cli.md`; the tests check that the page lists all of them.
Only modules in `cli/commands/` are loaded: other packages can't add
subcommands yet (that would need entry points).

The [CLI reference](tools/cli.md#reference) is generated from the parser
when the documentation is built (`docs_hooks/cli_reference.py`), so it
needs no update; describe new conventions or exit codes in
`docs/tools/cli.md`.

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
check-jsonschema --check-metaschema schemas/vocabularies/*.schema.json
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
