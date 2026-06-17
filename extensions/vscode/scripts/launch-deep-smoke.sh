#!/usr/bin/env bash

# Launch the AIIR deep smoke test against prepared fixtures.
#
# Prerequisites:
#   1. Run scripts/prepare-deep-smoke.sh to stage fixtures and VSIX.
#   2. Ensure code-insiders is available.
#
# Usage:
#   bash scripts/launch-deep-smoke.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_ROOT="${AIIR_SMOKE_PROFILE_ROOT:-/tmp/aiir-smoke-profile}"
FIXTURE_ROOT="${AIIR_SMOKE_FIXTURE_ROOT:-/tmp/aiir-smoke-fixtures}"
USER_DIR="$PROFILE_ROOT/user"
EXT_DIR="$PROFILE_ROOT/exts"
HEALTHY_DIR="$FIXTURE_ROOT/healthy"
WORKSPACE_FILE="$FIXTURE_ROOT/multi-root.code-workspace"
CODE_BIN="${CODE_INSIDERS_BIN:-$(command -v code-insiders || true)}"
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"

PACKAGE_VERSION="$($NODE_BIN -p "require(process.argv[1]).version" "$ROOT/package.json")"
VSIX_PATH="$ROOT/aiir-$PACKAGE_VERSION.vsix"

if [[ ! -f "$VSIX_PATH" ]]; then
	echo "Missing VSIX: $VSIX_PATH" >&2
	echo "Run: npm run package   (from $ROOT)" >&2
	exit 1
fi

if [[ ! -d "$HEALTHY_DIR" ]]; then
	echo "Missing healthy fixture: $HEALTHY_DIR" >&2
	echo "Run: bash $ROOT/scripts/prepare-deep-smoke.sh" >&2
	exit 1
fi

echo "==> Installing VSIX into smoke profile"
"$CODE_BIN" \
	--user-data-dir "$USER_DIR" \
	--extensions-dir "$EXT_DIR" \
	--install-extension "$VSIX_PATH" \
	--force

echo "==> Launching VS Code with smoke fixtures"
echo "    VSIX:      $VSIX_PATH"
echo "    Healthy:   $HEALTHY_DIR"
echo "    Profile:   $PROFILE_ROOT"

if [[ -f "$WORKSPACE_FILE" ]]; then
	"$CODE_BIN" \
		--user-data-dir "$USER_DIR" \
		--extensions-dir "$EXT_DIR" \
		"$WORKSPACE_FILE"
else
	"$CODE_BIN" \
		--user-data-dir "$USER_DIR" \
		--extensions-dir "$EXT_DIR" \
		"$HEALTHY_DIR"
fi
