# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

# The live demo on a laptop (see docs/adoption/testbed.md): Docker with
# Compose v2 and nothing else. `make demo` builds and starts it and waits
# until it's healthy; `make demo-down` stops it.
#
# Ports, if 8000 or 8080 are taken: make demo DEMO_PORT=18000 DEMO_TRS_PORT=18080

COMPOSE = docker compose -f prototype/compose.yaml
DEMO_PORT ?= 8000
DEMO_TRS_PORT ?= 8080
# The stub runs as the user running make (under sudo, the user who called
# sudo), so that it can read examples/ even if the checkout isn't readable by
# others (e.g., cloned with umask 077)
DEMO_UID ?= $(or $(SUDO_UID),$(shell id -u))
DEMO_GID ?= $(or $(SUDO_GID),$(shell id -g))
PYTHON ?= python3
export DEMO_PORT DEMO_TRS_PORT DEMO_UID DEMO_GID

.PHONY: help demo demo-start demo-logs demo-down demo-clean demo-checksums

help:
	@echo "make demo            build and start the demo, then open http://127.0.0.1:$(DEMO_PORT)/"
	@echo "make demo-start      start the demo without building, e.g., offline"
	@echo "make demo-logs       follow the logs of the stub and the host"
	@echo "make demo-down       stop the demo and remove its containers"
	@echo "make demo-clean      as demo-down, and remove the image too"
	@echo "make demo-checksums  set the checksums of examples/workflows/ after editing a descriptor"

# What to open, once the stack is up
define DEMO_URLS
	@echo
	@echo "The demo is running: open http://127.0.0.1:$(DEMO_PORT)/"
	@echo "TRS stub: http://127.0.0.1:$(DEMO_TRS_PORT)/ga4gh/trs/v2/tools"
	@echo "Edit examples/workflows/*/ga4gh-io.schema.json and reload the page."
	@echo "Logs: make demo-logs. Stop: make demo-down."
endef

# TRS_URL and WES_URL of the shell or of a .env file would point the stack
# elsewhere: empty values override both, and compose.yaml then uses its
# defaults
LOCAL_ONLY = env TRS_URL= WES_URL=

demo:
	$(LOCAL_ONLY) $(COMPOSE) up --detach --build --wait
	$(DEMO_URLS)

# The image of an earlier `make demo`, without a network
demo-start:
	$(LOCAL_ONLY) $(COMPOSE) up --detach --no-build --pull never --wait
	$(DEMO_URLS)

demo-logs:
	$(COMPOSE) logs --follow

demo-down:
	$(COMPOSE) down

demo-clean:
	$(COMPOSE) down --rmi all

demo-checksums:
	$(PYTHON) examples/demo/checksums.py
