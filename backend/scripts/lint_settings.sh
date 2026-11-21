#!/usr/bin/env sh
set -eu

if grep -R "core\.numbering\|app\.core\.numbering\|legacy_next_number" -n app --include='*.py'; then
  echo "Forbidden legacy numbering import found" >&2
  exit 1
fi

if grep -R "AppSetting" -n app/modules --include='*.py' | grep -v "app/modules/settings/"; then
  echo "Direct AppSetting access outside settings module found" >&2
  exit 1
fi

python_bin="${PYTHON:-.venv/bin/python}"
if [ ! -x "$python_bin" ]; then
  python_bin=python3
fi
"$python_bin" scripts/scan_settings_leaks.py

echo "Settings lint OK"
