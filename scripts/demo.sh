#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m scopereceipt scan examples
python -m scopereceipt read contract.txt --start 1 --end 2
if python -m scopereceipt report --strict; then
  echo 'Unexpected: incomplete corpus passed!' >&2
  exit 1
fi
python -m scopereceipt read contract.txt --start 3 --end 3
python -m scopereceipt read notes.md --start 1 --end 3
python -m scopereceipt report --strict
