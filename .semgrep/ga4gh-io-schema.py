# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

"""Test cases of the semgrep rules in `ga4gh-io-schema.yml` (not run)."""

import urllib.request
from urllib.request import urlopen

import yaml

s = u = request = None

# ruleid: yaml-load-without-safe-loader
yaml.load(s)
# ruleid: yaml-load-without-safe-loader
yaml.load(s, Loader=yaml.FullLoader)
# ruleid: yaml-load-without-safe-loader
yaml.load_all(s)
# ruleid: yaml-load-without-safe-loader
yaml.unsafe_load(s)
# ruleid: yaml-load-without-safe-loader
yaml.full_load(s)
# ok: yaml-load-without-safe-loader
yaml.load(s, Loader=yaml.SafeLoader)
# ok: yaml-load-without-safe-loader
yaml.load(s, yaml.SafeLoader)
# ok: yaml-load-without-safe-loader
yaml.load(s, Loader=yaml.CSafeLoader)
# ok: yaml-load-without-safe-loader
yaml.load_all(s, Loader=yaml.CSafeLoader)
# ok: yaml-load-without-safe-loader
yaml.load(stream=s, Loader=yaml.SafeLoader)
# ok: yaml-load-without-safe-loader
yaml.safe_load(s)

# ruleid: urlopen-without-timeout
urllib.request.urlopen(u)
# ruleid: urlopen-without-timeout
urlopen(request)
# ok: urlopen-without-timeout
urllib.request.urlopen(u, timeout=5)
# ok: urlopen-without-timeout
urlopen(request, timeout=5)
# ok: urlopen-without-timeout
urllib.request.urlopen(u, None, 10)
