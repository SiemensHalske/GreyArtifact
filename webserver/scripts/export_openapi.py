#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from app import create_app
from app.extensions import api


def main() -> None:
    parser = argparse.ArgumentParser(description="Export GreyArtifact OpenAPI JSON.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/openapi.json"),
        help="Output path relative to the current directory.",
    )
    args = parser.parse_args()
    app = create_app(
        {
            "TESTING": True,
            "JWT_SECRET_KEY": "openapi-export-only-not-a-runtime-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
        }
    )
    specification = api.spec.to_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(specification, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
