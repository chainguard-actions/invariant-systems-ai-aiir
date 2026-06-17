#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_ROOT="${AIIR_SMOKE_FIXTURE_ROOT:-/tmp/aiir-smoke-fixtures}"
CLI_BIN="${AIIR_CLI_BIN:-$HOME/.local/share/aiir-cli/bin/aiir}"
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
GIT_BIN="${GIT_BIN:-$(command -v git || true)}"

require_bin() {
	local bin="$1"
	local label="$2"
	if [[ -z "$bin" ]] || ! command -v "$bin" >/dev/null 2>&1; then
		echo "Missing required tool: $label" >&2
		exit 1
	fi
}

require_bin "$CLI_BIN" "aiir CLI"
require_bin "$NODE_BIN" "node"
require_bin "$GIT_BIN" "git"

create_repo() {
	local dest="$1"
	rm -rf "$dest"
	mkdir -p "$dest"
	(
		cd "$dest"
		git init -q
		git config user.name "AIIR Smoke"
		git config user.email "smoke@invariantsystems.io"
		cat > README.md <<'EOF'
# AIIR Smoke Fixture

Public-safe repository used for packaged extension capture and smoke validation.
EOF
		mkdir -p src
		cat > src/app.py <<'EOF'
def main():
    return "aiir smoke fixture"
EOF
		git add README.md src/app.py
		git commit -q -m "feat: stage smoke fixture"
	)
}

write_receipt_ledger() {
	local repo_dir="$1"
	local receipt_json
	receipt_json="$(find "$repo_dir/.aiir/receipts" -maxdepth 1 -name 'receipt_*.json' | head -n 1)"
	if [[ -z "$receipt_json" ]]; then
		echo "No receipt JSON found in $repo_dir/.aiir/receipts" >&2
		exit 1
	fi
	cat "$receipt_json" > "$repo_dir/.aiir/receipts.jsonl"
	printf '\n' >> "$repo_dir/.aiir/receipts.jsonl"
}

tamper_receipt() {
	local receipt_path="$1"
	"$NODE_BIN" - "$receipt_path" <<'EOF'
const fs = require('node:fs');
const filePath = process.argv[2];
const receipt = JSON.parse(fs.readFileSync(filePath, 'utf8'));
receipt.content_hash = 'sha256:' + '0'.repeat(64);
fs.writeFileSync(filePath, JSON.stringify(receipt, null, 2) + '\n', 'utf8');
EOF
}

mkdir -p "$FIXTURE_ROOT"

NO_SCAFFOLD_DIR="$FIXTURE_ROOT/no-scaffold"
INITIALIZED_EMPTY_DIR="$FIXTURE_ROOT/initialized-empty"
INVALID_RECEIPT_DIR="$FIXTURE_ROOT/invalid-receipt"

echo "==> Creating no-scaffold fixture"
create_repo "$NO_SCAFFOLD_DIR"

echo "==> Creating initialized-empty fixture"
rm -rf "$INITIALIZED_EMPTY_DIR"
cp -R "$NO_SCAFFOLD_DIR" "$INITIALIZED_EMPTY_DIR"
(
	cd "$INITIALIZED_EMPTY_DIR"
	"$CLI_BIN" --init --policy balanced >/dev/null
	mkdir -p .aiir
	touch .aiir/editor_provenance.jsonl
)

echo "==> Creating invalid-receipt fixture"
rm -rf "$INVALID_RECEIPT_DIR"
cp -R "$INITIALIZED_EMPTY_DIR" "$INVALID_RECEIPT_DIR"
(
	cd "$INVALID_RECEIPT_DIR"
	"$CLI_BIN" --pretty --output .aiir/receipts >/dev/null
	write_receipt_ledger "$INVALID_RECEIPT_DIR"
	tamper_receipt "$(find .aiir/receipts -maxdepth 1 -name 'receipt_*.json' | head -n 1)"
	tamper_receipt .aiir/receipts.jsonl
	git add .aiir
	git commit -q -m "chore: add invalid receipt fixture"
)

echo "Fixtures ready under $FIXTURE_ROOT"
