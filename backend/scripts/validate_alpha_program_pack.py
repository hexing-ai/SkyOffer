from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.services.alpha_program_pack_validator import (
    AlphaProgramPackValidationError,
    validate_alpha_program_pack_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate one alpha_program_pack.v1 without network or database access."
    )
    parser.add_argument("pack", type=Path)
    parser.add_argument("--scope", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = validate_alpha_program_pack_files(
            pack_path=args.pack, scope_path=args.scope
        )
    except AlphaProgramPackValidationError as exc:
        print(json.dumps({"valid": False, "issues": exc.issues}, ensure_ascii=False))
        return 1
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
