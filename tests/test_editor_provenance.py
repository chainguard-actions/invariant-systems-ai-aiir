"""Tests for editor provenance queue consumption and receipt attachment."""

# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import pytest

import aiir.cli as cli
import aiir._editor_provenance as editor_provenance
from aiir._editor_provenance import consume_editor_provenance
from aiir._receipt import build_commit_receipt
from aiir._core import CommitInfo


def _make_commit() -> CommitInfo:
    return CommitInfo(
        sha="a" * 40,
        tree_sha="b" * 40,
        parent_shas=["c" * 40],
        author_name="Example Author",
        author_email="author@example.com",
        author_date="2026-03-13T00:00:00Z",
        committer_name="Example Committer",
        committer_email="committer@example.com",
        committer_date="2026-03-13T00:00:00Z",
        subject="Example change",
        body="Example body",
        diff_stat="1 file changed, 1 insertion(+)",
        diff_hash="sha256:" + "d" * 64,
        files_changed=["src/example.ts"],
        is_ai_authored=False,
        ai_signals_detected=[],
        is_bot_authored=False,
        bot_signals_detected=[],
        authorship_class="human",
    )


def test_consume_editor_provenance_builds_receipt_payload_and_compacts_queue(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    base_record = {
        "id": "rec-1",
        "sessionId": "session-1",
        "createdAt": "2026-03-13T00:00:00Z",
        "repositoryPath": "/tmp/repo",
        "branch": "main",
        "baseCommitSha": "0" * 40,
        "toolId": "aiir-vscode",
        "mode": "provable",
        "command": "generate",
        "modelVendor": "copilot",
        "modelFamily": "gpt-4.1",
        "source": "aiir-command",
        "promptKind": "file",
        "files": [
            {
                "path": "src/example.ts",
                "beforeHash": "sha256:" + "1" * 64,
                "afterHash": "sha256:" + "2" * 64,
            }
        ],
        "previousRecordHash": None,
        "applied": True,
        "consumed": False,
    }
    hash_input = {k: v for k, v in base_record.items() if k != "contentHash"}
    import aiir._editor_provenance as editor_provenance

    base_record["contentHash"] = editor_provenance._hash_record(hash_input)
    queue_path.write_text(json.dumps(base_record) + "\n", encoding="utf-8")

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="f" * 40
    )

    assert changed is True
    assert payload == {
        "schema": "aiir/editor_provenance.v1",
        "mode": "provable",
        "toolId": "aiir-vscode",
        "recordCount": 1,
        "chainHead": base_record["contentHash"],
        "merkleRoot": base_record["contentHash"],
        "records": [
            {
                "id": "rec-1",
                "command": "generate",
                "source": "aiir-command",
                "promptKind": "file",
                "createdAt": "2026-03-13T00:00:00Z",
                "sessionId": "session-1",
                "branch": "main",
                "baseCommitSha": "0" * 40,
                "modelVendor": "copilot",
                "modelFamily": "gpt-4.1",
                "contentHash": base_record["contentHash"],
                "files": [
                    {
                        "path": "src/example.ts",
                        "beforeHash": "sha256:" + "1" * 64,
                        "afterHash": "sha256:" + "2" * 64,
                    }
                ],
            }
        ],
    }
    assert queue_path.read_text(encoding="utf-8") == ""


def test_build_commit_receipt_includes_editor_provenance_extension() -> None:
    receipt = build_commit_receipt(
        _make_commit(),
        editor_provenance={
            "schema": "aiir/editor_provenance.v1",
            "mode": "provable",
            "toolId": "aiir-vscode",
            "recordCount": 1,
            "chainHead": "sha256:" + "3" * 64,
            "merkleRoot": "sha256:" + "3" * 64,
            "records": [
                {
                    "id": "rec-1",
                    "command": "generate",
                    "files": [
                        {
                            "path": "src/example.ts",
                            "beforeHash": "sha256:" + "1" * 64,
                            "afterHash": "sha256:" + "2" * 64,
                        }
                    ],
                }
            ],
        },
    )

    assert receipt["extensions"]["editor_provenance"]["mode"] == "provable"
    assert receipt["extensions"]["editor_provenance"]["toolId"] == "aiir-vscode"
    assert (
        receipt["extensions"]["editor_provenance"]["schema"]
        == "aiir/editor_provenance.v1"
    )


def test_consume_editor_provenance_merges_multiple_active_records(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    records = []
    import aiir._editor_provenance as editor_provenance

    for index in range(2):
        record = {
            "id": f"rec-{index}",
            "sessionId": "session-1",
            "createdAt": "2026-03-13T00:00:00Z",
            "repositoryPath": "/tmp/repo",
            "toolId": "aiir-vscode",
            "mode": "provable",
            "command": "generate",
            "source": "aiir-command",
            "promptKind": "file",
            "files": [],
            "previousRecordHash": records[-1]["contentHash"] if records else None,
            "applied": True,
            "consumed": False,
        }
        record["contentHash"] = editor_provenance._hash_record(
            {k: v for k, v in record.items() if k != "contentHash"}
        )
        records.append(record)

    queue_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="f" * 40
    )

    assert changed is True
    assert payload["schema"] == "aiir/editor_provenance.v1"
    assert payload["mode"] == "provable"
    assert payload["toolId"] == "aiir-vscode"
    assert payload["recordCount"] == 2
    assert payload["chainHead"] == records[-1]["contentHash"]
    assert payload["merkleRoot"]
    assert payload["records"] == [
        {
            "id": "rec-0",
            "command": "generate",
            "source": "aiir-command",
            "promptKind": "file",
            "createdAt": "2026-03-13T00:00:00Z",
            "sessionId": "session-1",
            "contentHash": records[0]["contentHash"],
            "files": [],
        },
        {
            "id": "rec-1",
            "command": "generate",
            "source": "aiir-command",
            "promptKind": "file",
            "createdAt": "2026-03-13T00:00:00Z",
            "sessionId": "session-1",
            "previousRecordHash": records[0]["contentHash"],
            "contentHash": records[1]["contentHash"],
            "files": [],
        },
    ]
    assert queue_path.read_text(encoding="utf-8") == ""


def test_consume_editor_provenance_keeps_records_for_current_head(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    records = []
    import aiir._editor_provenance as editor_provenance

    for index, base_commit_sha in enumerate(["0" * 40, "f" * 40]):
        record = {
            "id": f"rec-{index}",
            "sessionId": "session-1",
            "createdAt": "2026-03-13T00:00:00Z",
            "repositoryPath": "/tmp/repo",
            "baseCommitSha": base_commit_sha,
            "toolId": "aiir-vscode",
            "mode": "provable",
            "command": "generate",
            "source": "aiir-command",
            "promptKind": "file",
            "files": [],
            "previousRecordHash": records[-1]["contentHash"] if records else None,
            "applied": True,
            "consumed": False,
        }
        record["contentHash"] = editor_provenance._hash_record(
            {k: v for k, v in record.items() if k != "contentHash"}
        )
        records.append(record)

    queue_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="f" * 40
    )

    assert changed is True
    assert payload == {
        "schema": "aiir/editor_provenance.v1",
        "mode": "provable",
        "toolId": "aiir-vscode",
        "recordCount": 1,
        "chainHead": records[0]["contentHash"],
        "merkleRoot": records[0]["contentHash"],
        "records": [
            {
                "id": "rec-0",
                "command": "generate",
                "source": "aiir-command",
                "promptKind": "file",
                "createdAt": "2026-03-13T00:00:00Z",
                "sessionId": "session-1",
                "baseCommitSha": "0" * 40,
                "contentHash": records[0]["contentHash"],
                "files": [],
            }
        ],
    }
    remaining = queue_path.read_text(encoding="utf-8")
    assert '"id":"rec-1"' in remaining
    assert '"id":"rec-0"' not in remaining

    remaining_records = [
        json.loads(line) for line in remaining.splitlines() if line.strip()
    ]
    assert len(remaining_records) == 1
    assert remaining_records[0]["id"] == "rec-1"
    assert remaining_records[0]["previousRecordHash"] is None

    expected_hash = editor_provenance._hash_record(
        {k: v for k, v in remaining_records[0].items() if k != "contentHash"}
    )
    assert remaining_records[0]["contentHash"] == expected_hash


def test_consume_editor_provenance_rechains_remaining_records_after_compaction(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    records = []

    for index, base_commit_sha in enumerate(["0" * 40, "1" * 40, "f" * 40]):
        record = {
            "id": f"rec-{index}",
            "sessionId": "session-1",
            "createdAt": "2026-03-13T00:00:00Z",
            "repositoryPath": "/tmp/repo",
            "baseCommitSha": base_commit_sha,
            "toolId": "aiir-vscode",
            "mode": "provable",
            "command": "generate",
            "source": "aiir-command",
            "promptKind": "file",
            "files": [],
            "previousRecordHash": records[-1]["contentHash"] if records else None,
            "applied": True,
            "consumed": False,
        }
        record["contentHash"] = editor_provenance._hash_record(
            {k: v for k, v in record.items() if k != "contentHash"}
        )
        records.append(record)

    queue_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="f" * 40
    )

    assert changed is True
    assert payload is not None
    assert payload["recordCount"] == 2

    remaining_records = [
        json.loads(line)
        for line in queue_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [record["id"] for record in remaining_records] == ["rec-2"]
    assert remaining_records[0]["previousRecordHash"] is None

    expected_hash = editor_provenance._hash_record(
        {k: v for k, v in remaining_records[0].items() if k != "contentHash"}
    )
    assert remaining_records[0]["contentHash"] == expected_hash

    next_payload, next_changed = consume_editor_provenance(
        str(queue_path), current_head_sha="a" * 40
    )
    assert next_changed is True
    assert next_payload is not None
    assert next_payload["records"][0]["id"] == "rec-2"


def test_consume_editor_provenance_defers_when_still_on_base_commit(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    import aiir._editor_provenance as editor_provenance

    record = {
        "id": "rec-1",
        "sessionId": "session-1",
        "createdAt": "2026-03-13T00:00:00Z",
        "repositoryPath": "/tmp/repo",
        "baseCommitSha": "a" * 40,
        "toolId": "aiir-vscode",
        "mode": "provable",
        "command": "generate",
        "source": "aiir-command",
        "promptKind": "file",
        "files": [],
        "previousRecordHash": None,
        "applied": True,
        "consumed": False,
    }
    record["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in record.items() if k != "contentHash"}
    )
    queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="a" * 40
    )

    assert payload is None
    assert changed is False
    assert queue_path.read_text(encoding="utf-8").strip()


def test_cli_init_gitignore_includes_editor_provenance_entry(tmp_path: Path) -> None:
    ledger_dir = tmp_path / ".aiir"
    with patch("pathlib.Path.cwd", return_value=tmp_path.resolve()):
        rc = cli.main(["--init", "--ledger", str(ledger_dir)])

    assert rc == 0
    gitignore = (ledger_dir / ".gitignore").read_text(encoding="utf-8")
    assert "editor_provenance.jsonl" in gitignore


def test_consume_editor_provenance_returns_none_for_missing_queue(
    tmp_path: Path,
) -> None:
    payload, changed = consume_editor_provenance(str(tmp_path / "missing.jsonl"))

    assert payload is None
    assert changed is False


def test_consume_editor_provenance_rejects_non_object_record(tmp_path: Path) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    queue_path.write_text('"not-an-object"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="non-object"):
        consume_editor_provenance(str(queue_path))


def test_editor_provenance_skips_blank_lines_and_handles_empty_merkle_root(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    record = {
        "id": "rec-1",
        "files": [],
        "previousRecordHash": None,
        "consumed": False,
    }
    record["contentHash"] = editor_provenance._hash_record(record)
    queue_path.write_text("\n  \n" + json.dumps(record) + "\n", encoding="utf-8")

    payload, changed = consume_editor_provenance(str(queue_path))

    assert changed is True
    assert payload is not None
    assert editor_provenance._merkle_root([]) == "sha256:" + editor_provenance._sha256(
        ""
    )


def test_consume_editor_provenance_rejects_missing_and_tampered_content_hash(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    missing_hash = {
        "id": "rec-1",
        "files": [],
        "previousRecordHash": None,
        "consumed": False,
    }
    queue_path.write_text(json.dumps(missing_hash) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing contentHash"):
        consume_editor_provenance(str(queue_path))

    tampered = dict(missing_hash)
    tampered["contentHash"] = "sha256:" + "0" * 64
    queue_path.write_text(json.dumps(tampered) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="failed content-hash validation"):
        consume_editor_provenance(str(queue_path))


def test_consume_editor_provenance_rejects_broken_hash_chain(tmp_path: Path) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    first = {
        "id": "rec-1",
        "files": [],
        "previousRecordHash": "sha256:" + "9" * 64,
        "consumed": False,
    }
    first["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in first.items() if k != "contentHash"}
    )
    queue_path.write_text(json.dumps(first) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="broken hash chain at the first record"):
        consume_editor_provenance(str(queue_path))

    first["previousRecordHash"] = None
    first["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in first.items() if k != "contentHash"}
    )
    second = {
        "id": "rec-2",
        "files": [],
        "previousRecordHash": "sha256:" + "8" * 64,
        "consumed": False,
    }
    second["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in second.items() if k != "contentHash"}
    )
    queue_path.write_text(
        json.dumps(first) + "\n" + json.dumps(second) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="broken hash chain at record 2"):
        consume_editor_provenance(str(queue_path))


def test_consume_editor_provenance_repairs_legacy_orphaned_queue_head(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    records = []

    for index in range(2):
        record = {
            "id": f"rec-{index}",
            "files": [],
            "previousRecordHash": records[-1]["contentHash"] if records else None,
            "consumed": False,
        }
        record["contentHash"] = editor_provenance._hash_record(
            {k: v for k, v in record.items() if k != "contentHash"}
        )
        records.append(record)

    records[0]["previousRecordHash"] = "sha256:" + "9" * 64
    records[0]["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in records[0].items() if k != "contentHash"}
    )
    records[1]["previousRecordHash"] = records[0]["contentHash"]
    records[1]["contentHash"] = editor_provenance._hash_record(
        {k: v for k, v in records[1].items() if k != "contentHash"}
    )

    queue_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )

    payload, changed = consume_editor_provenance(
        str(queue_path), current_head_sha="f" * 40
    )

    assert changed is True
    assert payload is not None
    assert payload["recordCount"] == 2
    assert queue_path.read_text(encoding="utf-8") == ""


def test_build_receipt_payload_validates_file_shapes() -> None:
    with pytest.raises(ValueError, match="files must be a list"):
        editor_provenance._build_receipt_record({"files": "bad"})

    with pytest.raises(ValueError, match="file entry must be an object"):
        editor_provenance._build_receipt_record({"files": ["bad"]})

    with pytest.raises(ValueError, match="missing required fields"):
        editor_provenance._build_receipt_record({"files": [{"path": "x"}]})


def test_build_receipt_payload_and_all_consumed_queue_paths(tmp_path: Path) -> None:
    record = {
        "id": "rec-1",
        "files": [],
        "consumed": True,
    }
    record["contentHash"] = editor_provenance._hash_record(record)

    payload = editor_provenance._build_receipt_payload(record)
    assert payload["recordCount"] == 1
    assert payload["chainHead"] == record["contentHash"]
    assert payload["merkleRoot"] == record["contentHash"]

    queue_path = tmp_path / "editor_provenance.jsonl"
    queue_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    consumed_payload, changed = consume_editor_provenance(str(queue_path))
    assert consumed_payload is None
    assert changed is False


def test_repair_orphaned_queue_head_rejects_invalid_inputs() -> None:
    valid_head = {
        "id": "rec-1",
        "files": [],
        "previousRecordHash": "sha256:" + "9" * 64,
    }
    valid_head["contentHash"] = editor_provenance._hash_record(valid_head)

    valid_tail = {
        "id": "rec-2",
        "files": [],
        "previousRecordHash": valid_head["contentHash"],
    }
    valid_tail["contentHash"] = editor_provenance._hash_record(valid_tail)

    assert editor_provenance._repair_orphaned_queue_head([valid_head]) is None

    missing_orphan_marker = [dict(valid_head), dict(valid_tail)]
    missing_orphan_marker[0]["previousRecordHash"] = None
    assert editor_provenance._repair_orphaned_queue_head(missing_orphan_marker) is None

    missing_content_hash = [dict(valid_head), dict(valid_tail)]
    missing_content_hash[0]["contentHash"] = ""
    assert editor_provenance._repair_orphaned_queue_head(missing_content_hash) is None

    mismatched_content_hash = [dict(valid_head), dict(valid_tail)]
    mismatched_content_hash[0]["contentHash"] = "sha256:" + "1" * 64
    assert (
        editor_provenance._repair_orphaned_queue_head(mismatched_content_hash) is None
    )

    broken_chain = [dict(valid_head), dict(valid_tail)]
    broken_chain[1]["previousRecordHash"] = "sha256:" + "2" * 64
    broken_chain[1]["contentHash"] = editor_provenance._hash_record(broken_chain[1])
    assert editor_provenance._repair_orphaned_queue_head(broken_chain) is None


def test_cli_editor_provenance_rejects_range_generation(tmp_path: Path) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    queue_path.write_text("", encoding="utf-8")
    stderr = io.StringIO()

    with redirect_stderr(stderr):
        rc = cli.main(
            [
                "--range",
                "HEAD~1..HEAD",
                "--editor-provenance",
                str(queue_path),
            ]
        )

    assert rc == 1
    assert "single-commit receipt generation" in stderr.getvalue()


def test_cli_editor_provenance_reports_invalid_queue(tmp_path: Path) -> None:
    queue_path = tmp_path / "editor_provenance.jsonl"
    queue_path.write_text('"bad-record"\n', encoding="utf-8")
    stderr = io.StringIO()

    with (
        patch("aiir.cli._run_git", side_effect=RuntimeError("git missing")),
        redirect_stderr(stderr),
    ):
        rc = cli.main(["-c", "HEAD", "--editor-provenance", str(queue_path)])

    assert rc == 1
    assert "non-object record" in stderr.getvalue()
