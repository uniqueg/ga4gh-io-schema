# Tools

- [Command-line interface](cli.md): the `ga4gh-io-schema` command, with
  one subcommand per tool.
- [Validator](validator.md): checks IO schemas against the
  [meta-schema](../specification/meta-schema.md), as a command-line tool and a
  Python API.
- [Converters](converters.md): translate the parameter descriptions of
  workflow languages into IO schemas (planned).
- [WES parameters](wes-params.md): validate input values against an IO
  schema and translate them into the `workflow_params` of a WES run request,
  or a full `RunRequest`, as a command-line tool and a Python API.
