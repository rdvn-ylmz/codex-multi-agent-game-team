#!/usr/bin/env bash
set -euo pipefail

python3 scripts/perf_smoke.py --iterations 120 --stages 6 --threshold-ms 2500
