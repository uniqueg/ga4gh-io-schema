# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""JSON over HTTP for the demo scripts, with the standard library only.

Access tokens come from environment variables, never from the command line,
so that they don't end up in the shell history or the process list, and
they are never printed.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any

#: Seconds to wait for a response.
TIMEOUT = 30


class HTTPError(RuntimeError):
    """A request failed: no connection, an error status or no JSON."""


def request_json(
    method: str,
    url: str,
    body: Any = None,
    token_env: str | None = None,
) -> Any:
    """Send a request and return the JSON body of the response.

    Args:
        method: HTTP method, e.g. ``GET``.
        url: URL of the request; ``http`` or ``https`` only.
        body: JSON body of the request, if any.
        token_env: Name of an environment variable with a bearer token; if
            it is set and not empty, the token is sent in ``Authorization``.

    Returns:
        The parsed body of the response.

    Raises:
        HTTPError: If the URL isn't ``http`` or ``https``, the request fails,
            the status isn't 2xx, or the body isn't JSON.
    """
    if not url.startswith(("http://", "https://")):
        raise HTTPError(f"Not an http or https URL: {url}")
    headers = {"Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    token = os.environ.get(token_env, "") if token_env else ""
    if token:
        # Not sent again if the server redirects, possibly to another host
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPError(f"{method} {url}: HTTP {exc.code}: {detail}") from exc
    except OSError as exc:  # also URLError and timeouts
        raise HTTPError(f"{method} {url}: {exc}") from exc
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise HTTPError(f"{method} {url}: the response isn't JSON") from exc
