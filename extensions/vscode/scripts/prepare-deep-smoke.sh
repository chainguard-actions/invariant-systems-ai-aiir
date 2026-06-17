#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_ROOT="${AIIR_SMOKE_PROFILE_ROOT:-/tmp/aiir-smoke-profile}"
FIXTURE_ROOT="${AIIR_SMOKE_FIXTURE_ROOT:-/tmp/aiir-smoke-fixtures}"
USER_DIR="$PROFILE_ROOT/user"
EXT_DIR="$PROFILE_ROOT/exts"
HEALTHY_DIR="$FIXTURE_ROOT/healthy"
WORKSPACE_FILE="$FIXTURE_ROOT/multi-root.code-workspace"
CLI_BIN="${AIIR_CLI_BIN:-$HOME/.local/share/aiir-cli/bin/aiir}"
CODE_BIN="${CODE_INSIDERS_BIN:-$(command -v code-insiders || true)}"
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"

require_bin() {
	local bin="$1"
	local label="$2"
	if [[ -z "$bin" ]] || ! command -v "$bin" >/dev/null 2>&1; then
		echo "Missing required tool: $label" >&2
		exit 1
	fi
}

require_bin "$NODE_BIN" "node"

PACKAGE_VERSION="$($NODE_BIN -p "require(process.argv[1]).version" "$ROOT/package.json")"
VSIX_PATH="$ROOT/aiir-$PACKAGE_VERSION.vsix"

require_bin "$CLI_BIN" "aiir CLI"
require_bin "$CODE_BIN" "code-insiders"

echo "==> Materializing smoke fixtures"
bash "$ROOT/scripts/materialize-deep-smoke-fixtures.sh"

for path in \
	"$FIXTURE_ROOT/no-scaffold" \
	"$FIXTURE_ROOT/initialized-empty" \
	"$FIXTURE_ROOT/invalid-receipt"; do
	if [[ ! -d "$path" ]]; then
		echo "Missing expected smoke fixture: $path" >&2
		echo "Recreate the fixtures before running the human smoke pass." >&2
		exit 1
	fi
done

if [[ ! -d "$FIXTURE_ROOT/initialized-empty/.aiir" ]]; then
	echo "Initialized-empty fixture is missing .aiir scaffolding: $FIXTURE_ROOT/initialized-empty" >&2
	exit 1
fi

echo "==> Staging neutral healthy fixture"
rm -rf "$HEALTHY_DIR"
cp -R "$FIXTURE_ROOT/initialized-empty" "$HEALTHY_DIR"

if [[ ! -d "$HEALTHY_DIR/.git" ]]; then
	echo "Healthy fixture staging failed: missing git metadata in $HEALTHY_DIR" >&2
	exit 1
fi

mkdir -p "$HEALTHY_DIR/.aiir/receipts"
touch "$HEALTHY_DIR/.aiir/editor_provenance.jsonl"

(
	cd "$HEALTHY_DIR"
	"$CLI_BIN" --pretty --output .aiir/receipts >/dev/null
)

HEALTHY_RECEIPT_JSON="$(find "$HEALTHY_DIR/.aiir/receipts" -maxdepth 1 -name 'receipt_*.json' | head -n 1)"
if [[ -z "$HEALTHY_RECEIPT_JSON" ]]; then
	echo "Healthy fixture staging failed: no receipt JSON created in $HEALTHY_DIR/.aiir/receipts" >&2
	exit 1
fi

cat "$HEALTHY_RECEIPT_JSON" > "$HEALTHY_DIR/.aiir/receipts.jsonl"
printf '\n' >> "$HEALTHY_DIR/.aiir/receipts.jsonl"

if [[ ! -d "$HEALTHY_DIR/.aiir/receipts" ]] || ! find "$HEALTHY_DIR/.aiir/receipts" -maxdepth 1 -name 'receipt_*.json' | grep -q .; then
	echo "Healthy fixture staging failed: no receipt artifacts created in $HEALTHY_DIR/.aiir/receipts" >&2
	exit 1
fi

mkdir -p "$PROFILE_ROOT" "$USER_DIR" "$EXT_DIR"

cat > "$WORKSPACE_FILE" <<EOF
{
	"folders": [
		{ "path": "$FIXTURE_ROOT/initialized-empty" },
		{ "path": "$FIXTURE_ROOT/invalid-receipt" }
	],
	"settings": {
		"workbench.startupEditor": "none",
		"aiir.enforceWorkspaceIsolation": true,
		"aiir.allowedWorkspaceFolders": []
	}
}
EOF

echo "==> Packaging current VSIX"
cd "$ROOT"
npm run package

if [[ ! -f "$VSIX_PATH" ]]; then
	echo "Expected VSIX not found after packaging: $VSIX_PATH" >&2
	exit 1
fi

echo "==> Installing VSIX into clean smoke profile"
"$CODE_BIN" \
	--user-data-dir "$USER_DIR" \
	--extensions-dir "$EXT_DIR" \
	--install-extension "$VSIX_PATH" \
	--force >/dev/null

echo "==> Verifying installed extension"
"$CODE_BIN" \
	--user-data-dir "$USER_DIR" \
	--extensions-dir "$EXT_DIR" \
	--list-extensions \
	--show-versions | grep '^invariant-systems\.aiir@'

echo "==> Verifying CLI"
"$CLI_BIN" --version

cat <<EOF

Deep smoke environment is ready.

Package version:
	$PACKAGE_VERSION

VSIX artifact:
	$VSIX_PATH

Profile:
  $PROFILE_ROOT

Fixtures:
	Healthy repo: $HEALTHY_DIR
  No scaffold: $FIXTURE_ROOT/no-scaffold
  Initialized empty: $FIXTURE_ROOT/initialized-empty
  Invalid receipt: $FIXTURE_ROOT/invalid-receipt
  Multi-root workspace: $WORKSPACE_FILE

Suggested next command:
  code-insiders --user-data-dir "$USER_DIR" --extensions-dir "$EXT_DIR" --skip-welcome --disable-workspace-trust --new-window

Update this report during the run:
  $ROOT/docs/release/DEEP_SMOKE_RUN_2026-03-15.md

Reference checklist:
	$ROOT/docs/release/BLOCKING_DEEP_SMOKE_CHECKLIST.md
EOF
