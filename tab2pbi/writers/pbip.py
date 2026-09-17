"""Write the root .pbip file and .gitignore.

The .pbip file is the entry point that Power BI Desktop uses
to open the project.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_pbip(output_dir: Path, name: str) -> Path:
    """Write the root .pbip file and .gitignore.

    Args:
        output_dir: Base output directory.
        name: Project name.

    Returns:
        Path to the .pbip file.
    """
    # Write .pbip file
    pbip_content = {
        "version": "1.0",
        "artifacts": [
            {
                "report": {
                    "path": f"{name}.Report"
                }
            }
        ],
        "settings": {
            "enableAutoRecovery": True
        }
    }

    pbip_path = output_dir / f"{name}.pbip"
    pbip_path.write_text(
        json.dumps(pbip_content, indent=2), encoding="utf-8"
    )

    # Write .gitignore
    gitignore_content = "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n"
    gitignore_path = output_dir / ".gitignore"
    gitignore_path.write_text(gitignore_content, encoding="utf-8")

    logger.info(f"Wrote {pbip_path}")
    return pbip_path
