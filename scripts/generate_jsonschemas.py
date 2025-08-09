"""
Generate JSON Schemas from Pydantic models for frontend/runtime validation.

Outputs schemas to incremental/schemas/ for consumption by Flutter or tests.
Run:
  python scripts/generate_jsonschemas.py
"""

from pathlib import Path
import sys
import json

# Ensure local package is importable when run from repo root/CI
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import eidolon.models as _eid_models  # type: ignore


def write_schema(model, out_dir: Path, name: str) -> None:
    # Emit schema using field aliases (PascalCase) to match API payloads
    schema = model.model_json_schema(by_alias=True)
    out = out_dir / f"{name}.schema.json"
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "incremental" / "schemas"
    out_dir.mkdir(parents=True, exist_ok=True)

    to_emit = [
        ("StorySegment", "story-segment"),
        ("ActiveSegment", "active-segment"),
        ("ChallengeAttempt", "challenge-attempt"),
        ("ChallengeResultModel", "challenge-result"),
        ("CombatAttack", "combat-attack"),
        ("CombatRound", "combat-round"),
        ("CombatStateModel", "combat-state"),
        ("ClientEvent", "client-event"),
    ]
    for attr, fname in to_emit:
        model = getattr(_eid_models, attr, None)
        if model is None:
            continue
        write_schema(model, out_dir, fname)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
