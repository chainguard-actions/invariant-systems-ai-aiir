#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2025-2026 Invariant Systems, Inc.
set -euo pipefail

COSIGN_VERSION="${COSIGN_VERSION:-v3.0.5}"
RUNNER_OS_VALUE="${RUNNER_OS:-Linux}"
RUNNER_ARCH_VALUE="${RUNNER_ARCH:-X64}"

# SHA256 checksums for cosign v3.0.5 — from cosign_checksums.txt in the release
COSIGN_SHA256_AMD64="db15cc99e6e4837daabab023742aaddc3841ce57f193d11b7c3e06c8003642b2"
COSIGN_SHA256_ARM64="d098f3168ae4b3aa70b4ca78947329b953272b487727d1722cb3cb098a1a20ab"

if [ "$RUNNER_OS_VALUE" != "Linux" ]; then
  echo "::error::install-cosign.sh only supports Linux runners (got ${RUNNER_OS_VALUE})"
  exit 1
fi

case "$RUNNER_ARCH_VALUE" in
  X64|x64|AMD64|amd64)
    COSIGN_ARCH="amd64"
    EXPECTED_SHA256="$COSIGN_SHA256_AMD64"
    ;;
  ARM64|arm64)
    COSIGN_ARCH="arm64"
    EXPECTED_SHA256="$COSIGN_SHA256_ARM64"
    ;;
  *)
    echo "::error::Unsupported runner architecture: ${RUNNER_ARCH_VALUE}"
    exit 1
    ;;
esac

INSTALL_DIR="${RUNNER_TEMP:-/tmp}/cosign-bin"
COSIGN_BIN="${INSTALL_DIR}/cosign"
COSIGN_URL="https://github.com/sigstore/cosign/releases/download/${COSIGN_VERSION}/cosign-linux-${COSIGN_ARCH}"

mkdir -p "$INSTALL_DIR"
curl -fsSL "$COSIGN_URL" -o "$COSIGN_BIN"

# Verify SHA256 checksum before trusting the binary
ACTUAL_SHA256="$(sha256sum "$COSIGN_BIN" | cut -d' ' -f1)"
if [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
  echo "::error::SHA256 mismatch for cosign-linux-${COSIGN_ARCH}: expected ${EXPECTED_SHA256}, got ${ACTUAL_SHA256}"
  exit 1
fi
echo "✅ SHA256 checksum verified: ${ACTUAL_SHA256}"

chmod 0755 "$COSIGN_BIN"

if [ -n "${GITHUB_PATH:-}" ]; then
  echo "$INSTALL_DIR" >> "$GITHUB_PATH"
fi

VERSION_OUTPUT="$($COSIGN_BIN version)"
printf '%s\n' "$VERSION_OUTPUT"

INSTALLED_VERSION="$(printf '%s\n' "$VERSION_OUTPUT" | sed -n 's/.*GitVersion:[[:space:]]*//p' | head -1)"
if [ "$INSTALLED_VERSION" != "$COSIGN_VERSION" ]; then
  echo "::error::Expected cosign ${COSIGN_VERSION}, found ${INSTALLED_VERSION:-unknown}"
  exit 1
fi

echo "✅ cosign ${COSIGN_VERSION} installed"
