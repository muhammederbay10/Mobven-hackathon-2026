#!/usr/bin/env sh
# YetkiCheck — safe demo reset (macOS/Linux).
#
# Restores the database, the runtime registry and demo uploads to their
# committed baseline (plan section 8.2). The extraction cache is deliberately
# preserved: GAP-11 pre-warms cases 2-4 during final rehearsal and the section 16
# runbook runs this reset immediately before the judged run.

set -eu

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$REPO_ROOT/.venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

cd "$REPO_ROOT"
exec "$PYTHON" -m api.services.demo_service
