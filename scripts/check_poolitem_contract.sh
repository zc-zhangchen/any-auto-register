#!/usr/bin/env bash
# One-shot CI gate for the PoolItem contract.
#
# Stages:
#   1. sync upstream fixture mirror with the authoritative source
#      (delegates to scripts/sync_poolitem_fixtures.sh)
#   2. run pytest tests/pools/ -v
#   3. validate every golden-samples.jsonl entry against
#      contracts/poolitem.schema.json with python-jsonschema
#
# Any non-zero exit from any stage propagates; the first failure
# stops the script. Designed to be the single command CI invokes.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> [1/3] sync_poolitem_fixtures.sh"
bash scripts/sync_poolitem_fixtures.sh

echo
echo "==> [2/3] pytest tests/pools/ -v"
python3 -m pytest tests/pools/ -v

echo
echo "==> [3/3] jsonschema validate golden-samples vs poolitem.schema.json"
python3 - <<'PY'
import json
import pathlib
import sys

try:
    import jsonschema
except ImportError:
    sys.stderr.write(
        "ERROR: jsonschema not installed. Run: pip install jsonschema\n"
    )
    sys.exit(2)

root = pathlib.Path(__file__).resolve().parent if "__file__" in globals() else pathlib.Path.cwd()
# Heredoc runs without __file__; resolve from cwd which is REPO_ROOT.
root = pathlib.Path.cwd()

schema_path = root / "specs/001-poolitem-contract/contracts/poolitem.schema.json"
fixture_path = root / "specs/001-poolitem-contract/contracts/golden-samples.jsonl"

schema = json.loads(schema_path.read_text(encoding="utf-8"))
# golden-samples.jsonl carries an extra "_case" label which the schema
# (additionalProperties: false) rejects. Strip it before validating.
validator = jsonschema.Draft202012Validator(schema)

fail = 0
total = 0
for raw in fixture_path.read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line:
        continue
    total += 1
    payload = {k: v for k, v in json.loads(line).items() if k != "_case"}
    errors = sorted(validator.iter_errors(payload), key=lambda e: e.path)
    if errors:
        fail += 1
        case = json.loads(line).get("_case", f"#{total}")
        print(f"  FAIL {case}:")
        for err in errors:
            print(f"    - {'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}")

if fail:
    sys.stderr.write(f"\n{fail}/{total} golden samples failed jsonschema validation\n")
    sys.exit(1)

print(f"  OK  {total} samples conform to poolitem.schema.json")
PY

echo
echo "==> All checks passed."
