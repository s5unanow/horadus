#!/usr/bin/env bash
set -euo pipefail

hooks_dir="${1:-.git/hooks}"
required_hooks=(pre-commit pre-push commit-msg)

missing_hooks=()
for hook_name in "${required_hooks[@]}"; do
  hook_path="${hooks_dir}/${hook_name}"
  if [[ ! -x "${hook_path}" ]]; then
    missing_hooks+=("${hook_name}")
  fi
done

if (( ${#missing_hooks[@]} > 0 )); then
  echo "Missing required executable git hook(s) in ${hooks_dir}: ${missing_hooks[*]}"
  echo "Run: make hooks"
  exit 1
fi

echo "Required git hooks installed: ${required_hooks[*]}"
