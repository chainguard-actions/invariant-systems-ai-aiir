#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_ROOT="${AIIR_SMOKE_PROFILE_ROOT:-/tmp/aiir-smoke-profile}"
FIXTURE_ROOT="${AIIR_SMOKE_FIXTURE_ROOT:-/tmp/aiir-smoke-fixtures}"
USER_DIR="$PROFILE_ROOT/user"
EXT_DIR="$PROFILE_ROOT/exts"
CAPTURE_DIR="${AIIR_MARKETPLACE_CAPTURE_DIR:-$ROOT/docs/release/marketplace-captures}"
READY_DIR="$PROFILE_ROOT/capture-ready"
CODE_BIN="${CODE_INSIDERS_BIN:-$(command -v code-insiders || true)}"
IMPORT_BIN="${IMPORT_BIN:-$(command -v import || true)}"
CHROME_BIN="${CHROME_BIN:-$(command -v google-chrome || true)}"
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
DEFAULT_CODE_USER_DATA_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Code - Insiders"

require_bin() {
	local bin="$1"
	local label="$2"
	if [[ -z "$bin" ]] || ! command -v "$bin" >/dev/null 2>&1; then
		echo "Missing required tool: $label" >&2
		exit 1
	fi
}

require_bin "$CODE_BIN" "code-insiders"
require_bin "$IMPORT_BIN" "ImageMagick import"
require_bin "$CHROME_BIN" "google-chrome"
require_bin "$NODE_BIN" "node"
require_bin "$(command -v xprop || true)" "xprop"
require_bin "$(command -v xwininfo || true)" "xwininfo"

mkdir -p "$CAPTURE_DIR" "$READY_DIR" "$USER_DIR/User"

bash "$ROOT/scripts/prepare-deep-smoke.sh"

write_settings() {
	local show_advanced="$1"
	cat > "$USER_DIR/User/settings.json" <<EOF
{
  "workbench.startupEditor": "none",
  "window.commandCenter": false,
  "workbench.editor.showTabs": true,
  "workbench.colorTheme": "Default Light Modern",
  "editor.minimap.enabled": false,
  "breadcrumbs.enabled": false,
  "aiir.showAdvancedCommands": $show_advanced,
  "aiir.strictLocalOnly": true
}
EOF
}

shutdown_capture_windows() {
	pkill -f "$USER_DIR" >/dev/null 2>&1 || true
	sleep 2
}

latest_main_log() {
	find "$USER_DIR/logs" -path '*/main.log' | sort | tail -n 1
}

main_log_has_enospc() {
	local main_log
	main_log="$(latest_main_log)"
	[[ -n "$main_log" ]] && grep -q 'ENOSPC: System limit for number of file watchers reached' "$main_log"
}

default_profile_session_detected() {
	pgrep -af -- "$DEFAULT_CODE_USER_DATA_DIR" >/dev/null 2>&1
}

report_capture_timeout_context() {
	local main_log
	main_log="$(latest_main_log)"
	if [[ -n "$main_log" ]] && grep -q 'ENOSPC: System limit for number of file watchers reached' "$main_log"; then
		echo "Capture session failed because Code Insiders hit the system file-watcher limit (ENOSPC). Close extra editor windows or raise fs.inotify.max_user_watches, then rerun." >&2
		if default_profile_session_detected; then
			echo "Detected an active Code Insiders session using $DEFAULT_CODE_USER_DATA_DIR; close that session before rerunning if you cannot raise the watcher limit." >&2
		fi
		echo "Relevant log: $main_log" >&2
		return
	fi

	if [[ -n "$main_log" ]]; then
		echo "Latest VS Code main log: $main_log" >&2
	fi
}

collect_candidate_pids() {
	local root_pid="$1"
	echo "$root_pid"
	pgrep -P "$root_pid" 2>/dev/null || true
}

find_window_id_for_title() {
	local window_title="$1"
	xwininfo -root -tree | awk -v title="$window_title" 'index($0, "\"" title "\"") { print $1; exit }'
}

find_window_id_for_pid() {
	local pid="$1"
	local window_ids
	window_ids="$(xwininfo -root -tree | awk '/Visual Studio Code/ { print $1 }')"
	for window_id in $window_ids; do
		local window_pid
		window_pid="$(xprop -id "$window_id" _NET_WM_PID 2>/dev/null | awk -F' = ' '{print $2}')"
		if [[ "$window_pid" == "$pid" ]]; then
			echo "$window_id"
			return 0
		fi
	 done
	return 1
}

	wait_for_window_id() {
	local launch_pid="$1"
	local window_title="$2"
	for _ in $(seq 1 120); do
		local titled_window_id
		titled_window_id="$(find_window_id_for_title "$window_title" || true)"
		if [[ -n "$titled_window_id" ]]; then
			echo "$titled_window_id"
			return 0
		fi

		while IFS= read -r pid; do
			if [[ -z "$pid" ]]; then
				continue
			fi
			local window_id
			window_id="$(find_window_id_for_pid "$pid" || true)"
			if [[ -n "$window_id" ]]; then
				echo "$window_id"
				return 0
			fi
		done < <(collect_candidate_pids "$launch_pid")
		sleep 1
	 done
	return 1
}

capture_surface() {
	local surface="$1"
	local target_path="$2"
	local show_advanced="$3"
	local base_name="$4"
	local ready_file="$READY_DIR/$surface.json"
	local png_path="$CAPTURE_DIR/$base_name.png"
	local window_title="$(basename "$target_path") - Visual Studio Code - Insiders"

	shutdown_capture_windows
	write_settings "$show_advanced"
	rm -f "$ready_file" "$png_path"

	env \
		AIIR_MARKETPLACE_CAPTURE_SURFACE="$surface" \
		AIIR_MARKETPLACE_CAPTURE_READY_FILE="$ready_file" \
		"$CODE_BIN" \
		--user-data-dir "$USER_DIR" \
		--extensions-dir "$EXT_DIR" \
		--skip-welcome \
		--disable-updates \
		--disable-workspace-trust \
		--new-window \
		"$target_path" >/dev/null 2>&1 &
	local launch_pid=$!

	for _ in $(seq 1 120); do
		if [[ -f "$ready_file" ]]; then
			break
		fi
		if main_log_has_enospc; then
			report_capture_timeout_context
			echo "Aborting $surface capture before timeout because Code Insiders cannot start with the current file-watcher limit" >&2
			exit 1
		fi
		sleep 1
	done

	if [[ ! -f "$ready_file" ]]; then
		report_capture_timeout_context
		echo "Timed out waiting for $surface capture readiness" >&2
		exit 1
	fi

	if grep -q '"status": "error"' "$ready_file"; then
		cat "$ready_file" >&2
		exit 1
	fi

	local window_id=""
	window_id="$(wait_for_window_id "$launch_pid" "$window_title" || true)"
	if [[ -z "$window_id" ]]; then
		echo "Timed out locating a Visual Studio Code window for $surface ($window_title)" >&2
		exit 1
	fi

	sleep 1
	"$IMPORT_BIN" -window "$window_id" "$png_path"
	shutdown_capture_windows
}

capture_surface "coverage" "$FIXTURE_ROOT/healthy" false "01-home-view"
capture_surface "setup" "$FIXTURE_ROOT/initialized-empty" false "02-setup-and-readiness"
capture_surface "receipts" "$FIXTURE_ROOT/healthy" false "03-receipt-explorer-and-viewer"
capture_surface "control" "$FIXTURE_ROOT/healthy" true "04-control-panel"
capture_surface "security" "$FIXTURE_ROOT/healthy" true "05-security-posture"
capture_surface "presets" "$FIXTURE_ROOT/healthy" true "06-deployment-presets"

"$NODE_BIN" "$ROOT/scripts/render-marketplace-capture-pdfs.js" "$CAPTURE_DIR"

for html_file in "$CAPTURE_DIR"/*.html; do
	base_name="$(basename "$html_file" .html)"
	"$CHROME_BIN" --headless --disable-gpu --no-sandbox \
		--print-to-pdf="$CAPTURE_DIR/$base_name.pdf" \
		"file://$html_file" >/dev/null 2>&1
done

echo "Marketplace capture pack ready in $CAPTURE_DIR"
