# Demo with TRS-Filer

The demo shows discovery with a real TRS implementation and the [proposed
`IO_SCHEMA` file type](trs.md#proposed-the-io_schema-file-type):
[TRS-Filer](https://github.com/elixir-cloud-aai/trs-filer) runs locally, the
[demo workflow](demo.md) is registered with its IO schema as a file of type
`IO_SCHEMA`, a client finds the schema among the files of the tool version
and checks it, and builds the WES run request. Nothing is submitted.

**Experimental:** TRS-Filer accepts `IO_SCHEMA` as an extension of TRS on
its development branch `dev`
([trs-filer#301](https://github.com/elixir-cloud-aai/trs-filer/pull/301)),
not yet in a release; released versions reject the registration with `400
Bad Request`. With `SCHEMA_FILE_TYPE=OTHER`, the demo registers the schema
as `OTHER` at `ga4gh-io.schema.json`, the fallback for TRS servers without
the type, and the client finds it there.

## What runs

[`examples/demo/trs-filer-demo.sh`](https://github.com/elixir-cloud-aai/ga4gh-io-schema/blob/main/examples/demo/trs-filer-demo.sh):

1. Starts TRS-Filer and MongoDB with TRS-Filer's Docker Compose setup, as a
   Compose project of its own (`io-schema-trs-filer-demo`), on
   `127.0.0.1` only, without authentication (TRS-Filer's
   `config.noauth.yaml`, for local development only).
2. Registers the tool `ga4gh-io-schema-demo`, version `1.0.0`, with
   [`register.py`](demo.md#1-register-the-workflow): the primary descriptor
   `demo.wdl` and the IO schema `ga4gh-io.schema.json` of type
   `IO_SCHEMA`.
3. Runs `trs_client.py`, a client built on the package, which follows
   [Discovery by clients](trs.md#discovery-by-clients):
    1. lists the files of the tool version for `WDL`;
    2. finds the IO schema with
       [`find_schema_file`](../tools/trs.md), by `file_type` and normalised
       `path` only;
    3. fetches it by its path and validates it against the profile (from
       the `content` of the `FileWrapper`; unlike the steps of the profile,
       the client doesn't fetch a schema that TRS serves only by `url`);
    4. checks `x-ga4gh-workflow` against the tool version, and its checksum
       against the `FileWrapper` of the primary descriptor;
    5. builds the run request from `values.json`, with the TRS URL of the
       plain primary descriptor as `workflow_url`
       ([`build_run_request`](../tools/wes-params.md)).
4. Stops TRS-Filer and removes its data. With `KEEP=1`, it leaves
   TRS-Filer running; stop it later with:

    ```bash
    docker compose --project-name io-schema-trs-filer-demo \
      --project-directory "$TRS_FILER_DIR" \
      -f "$TRS_FILER_DIR/docker-compose.yaml" down --volumes
    ```

## Running it

Prerequisites: Docker with Compose 2.24 or later (for `!override`), Git,
and Python with this package installed in a checkout of this repository
(`pip install -e .`). In Bash:

```bash
git clone https://github.com/elixir-cloud-aai/trs-filer.git ../trs-filer
TRS_FILER_DIR=../trs-filer TRS_FILER_PORT=8080 \
  examples/demo/trs-filer-demo.sh > run-request.json
```

| Variable | Meaning | Default |
| --- | --- | --- |
| `TRS_FILER_DIR` | Checkout of TRS-Filer | (required) |
| `TRS_FILER_PORT` | Port on `127.0.0.1` | `8080` |
| `SCHEMA_FILE_TYPE` | File type of the IO schema: `IO_SCHEMA` or `OTHER` | `IO_SCHEMA` |
| `REVISION` | Commit of this repository that the URL of the primary descriptor pins | `HEAD` |
| `PYTHON` | Python with this package | `python` |
| `KEEP` | `1` to leave TRS-Filer running | |

The steps go to standard error, the run request to standard output. The
first run builds TRS-Filer's image (a few minutes); later runs reuse it.

## Output

An example, with TRS-Filer with `IO_SCHEMA` (`dev`) on port 18082:

```text
== Register the demo workflow (IO schema of type IO_SCHEMA)
http://127.0.0.1:18082/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/WDL/descriptor/ga4gh-io.schema.json
== Find the IO schema as a client and build the run request
1. Files of the tool version: [{"file_type": "PRIMARY_DESCRIPTOR", "path": "demo.wdl"}, {"file_type": "IO_SCHEMA", "path": "ga4gh-io.schema.json"}]
2. IO schema: ga4gh-io.schema.json (file type IO_SCHEMA)
3. Valid against the profile: https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json
4. Bound to the tool version; checksum matches
5. Run request (not submitted):
```

```json
{
  "workflow_params": {
    "io_schema_demo.reads": "https://raw.githubusercontent.com/nf-core/test-datasets/3e548a3b34994380db1602506e0721fadbad6de1/data/genomics/sarscov2/illumina/bam/test.paired_end.bam",
    "io_schema_demo.min_mapq": 20,
    "io_schema_demo.read_filter": "proper_pairs"
  },
  "workflow_type": "WDL",
  "workflow_type_version": "1.1",
  "workflow_url": "http://127.0.0.1:18082/ga4gh/trs/v2/tools/ga4gh-io-schema-demo/versions/1.0.0/PLAIN_WDL/descriptor/demo.wdl"
}
```

With `SCHEMA_FILE_TYPE=OTHER`, step 1 lists `{"file_type": "OTHER", "path":
"ga4gh-io.schema.json"}`, step 2 reports `(file type OTHER)`, and the run
request is the same.

## Limits

- **Local only:** TRS-Filer runs without authentication, and the
  `workflow_url` points to `127.0.0.1`, which a WES elsewhere can't fetch
  (see [Can the WES fetch the
  `workflow_url`?](prototype-evaluation.md#where-the-spec-or-the-tools-fell-short)).
  To run the workflow, see the [end-to-end demo](demo.md).
- **Not in CI:** the script needs a checkout of TRS-Filer and builds its
  image, so it is run by hand. The client (`trs_client.py`) is tested
  against a mock server with both file types.
- **The check of TRS-Filer is off:** TRS-Filer can validate IO schemas when
  they are registered (`custom.io_schema.validation`), against the version
  of the profile that it vendors; the demo doesn't enable it.
- **TRS-Filer needs this state of the profile for its check:** the
  TRS-Filer `dev` branch vendors an earlier draft of version 0.3, whose
  `$id` (in the repository's former home, with a `v0.3.0` path segment) is
  not the `$id` of this profile, and which still requires `properties`.
  With its check on, that TRS-Filer rejects every schema of this
  repository, also `examples/demo/ga4gh-io.schema.json` (`$schema`
  doesn't match), and schemas written for its copy fail
  `ga4gh-io-schema validate`. Turn the check on only with a TRS-Filer that
  vendors the schemas of this repository, with the `$id`
  `https://raw.githubusercontent.com/elixir-cloud-aai/ga4gh-io-schema/main/schemas/ga4gh-io-profile.schema.json`.
