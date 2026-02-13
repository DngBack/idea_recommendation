"""
Simple checkpoint / resume support.
Stores intermediate state so a long generation run can be resumed.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _checkpoint_path(output_path: str) -> str:
    """Derive the checkpoint filename from the output JSON path."""
    return output_path + ".checkpoint.json"


def save_checkpoint(output_path: str, ideas: List[Dict], gen_idx: int) -> None:
    """Save current progress to a checkpoint file.

    Args:
        output_path: The final output JSON path (checkpoint is stored alongside it).
        ideas: List of idea dicts generated so far.
        gen_idx: The *next* generation index to start from on resume.
    """
    cp_path = _checkpoint_path(output_path)
    data = {
        "ideas": ideas,
        "gen_idx": gen_idx,
    }
    tmp_path = cp_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, cp_path)
    logger.debug("Checkpoint saved: %d ideas, gen_idx=%d -> %s", len(ideas), gen_idx, cp_path)


def load_checkpoint(output_path: str) -> Optional[Dict[str, Any]]:
    """Load a checkpoint file if it exists.

    Returns:
        A dict with keys ``ideas`` (list) and ``gen_idx`` (int), or None if
        no checkpoint exists.
    """
    cp_path = _checkpoint_path(output_path)
    if not os.path.exists(cp_path):
        return None

    try:
        with open(cp_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Loaded checkpoint from %s (%d ideas, gen_idx=%d)", cp_path, len(data.get("ideas", [])), data.get("gen_idx", 0))
        return data
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Corrupt checkpoint file %s: %s", cp_path, e)
        return None
