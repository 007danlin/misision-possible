#!/bin/zsh -l
set -eu
cd "$(dirname "$0")"
python3 scripts/local.py start
open http://127.0.0.1:18080
