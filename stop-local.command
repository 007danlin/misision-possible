#!/bin/zsh -l
set -eu
cd "$(dirname "$0")"
python3 scripts/local.py stop
