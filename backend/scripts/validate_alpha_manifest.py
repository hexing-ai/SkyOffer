from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.app.services.alpha_manifest_validator import (
    AlphaManifestValidationError,
    validate_alpha_manifest_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the Phase 4 scope snapshot and program manifest offline."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--require-publishable", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_alpha_manifest_files(
            root=args.root, require_publishable=args.require_publishable
        )
    except AlphaManifestValidationError as exc:
        print(
            json.dumps(
                {"valid": False, "issues": list(exc.issues)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {"valid": True, **report.model_dump(mode="json")},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
