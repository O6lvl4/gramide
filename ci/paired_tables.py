"""Release table loading and legacy source compatibility; no language packages."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ALMIDE = os.environ.get("ALMIDE_BIN", "almide")
FAILURES = {
    "triples": "v2 table: operation payload is not triples",
    "kind": "v2 table operation 0: unknown opcode",
    "index": "v2 table: invalid start operation",
}


def require(condition, description, process):
    if not condition:
        raise AssertionError(
            f"{description}\nexit: {process.returncode}"
            f"\nstdout: {process.stdout!r}\nstderr: {process.stderr!r}"
        )


def run(binary, mode):
    return subprocess.run(
        [str(binary), mode], cwd=ROOT, capture_output=True, timeout=30
    )


with tempfile.TemporaryDirectory(prefix="gramide-paired-tables-") as temp:
    binary = Path(temp) / "paired_tables"
    subprocess.run(
        [ALMIDE, "build", "ci/paired_tables.almd", "--release", "-o", str(binary)],
        cwd=ROOT, check=True, timeout=600,
    )
    valid = run(binary, "valid")
    require(valid.returncode == 0 and valid.stdout == b"paired table v2: ok\n"
            and valid.stderr == b"", "valid annotated v2 table failed to round-trip", valid)
    for mode, diagnostic in FAILURES.items():
        rejected = run(binary, mode)
        # Source line numbers may move. The complete failure message must not.
        expected = (
            rb"Error: assertion failed\n  at: line [0-9]+\n"
            rb"  expected: ok\(\(\)\)\n  found: err\(\""
            + re.escape(diagnostic.encode("utf-8")) + rb"\"\)\n"
        )
        require(rejected.returncode != 0 and rejected.stdout == b""
                and re.fullmatch(expected, rejected.stderr) is not None,
                f"{mode} did not fail closed with its exact diagnostic", rejected)
    legacy = run(binary, "legacy")
    expected_source = (ROOT / "ci/paired_tables_v1.almd.golden").read_bytes()
    require(legacy.returncode == 0 and legacy.stderr == b""
            and legacy.stdout == expected_source,
            "legacy table rendering changed; inspect the diff before updating the golden", legacy)

print("Paired table CI passed: valid v2 load, 3 release refusals, exact v1 rendering")
