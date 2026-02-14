"""
Command-line interface for the idea generator.
Usage:
    python -m idea_generator --topic-file topics/example_icbinb.md
    idea-generator --topic-file topics/example_icbinb.md   # if installed via pip
"""

import argparse
import logging
import sys

import yaml
from dotenv import load_dotenv

# Load .env from current directory so OPENAI_API_KEY etc. are set without manual export
load_dotenv()

from .core import IdeaGeneratorConfig, generate_ideas
from .llm import AVAILABLE_LLMS

logger = logging.getLogger("idea_generator")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stderr)


def _load_yaml_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="idea-generator",
        description="Generate AI research ideas from a topic description.",
    )
    parser.add_argument(
        "--topic-file",
        type=str,
        required=True,
        help="Path to a Markdown file describing the research topic.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to a YAML config file (overrides defaults, overridden by CLI flags).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path. Defaults to <topic-file>.json.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=f"LLM model to use. See AVAILABLE_LLMS for options.",
    )
    parser.add_argument(
        "--max-generations",
        type=int,
        default=None,
        help="Max number of ideas to generate.",
    )
    parser.add_argument(
        "--num-reflections",
        type=int,
        default=None,
        help="Number of reflection rounds per idea.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Resume from a previous checkpoint.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        default=False,
        help="Disable JSON schema validation for ideas.",
    )
    parser.add_argument(
        "--novelty-scoring",
        action="store_true",
        default=False,
        help="Enable novelty scoring for each idea.",
    )
    parser.add_argument(
        "--novelty-model",
        type=str,
        default=None,
        help="Model to use for novelty scoring (defaults to --model).",
    )
    parser.add_argument(
        "--no-arxiv",
        action="store_true",
        default=False,
        help="Disable the arXiv search tool.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)

    # Build config: defaults -> YAML file -> CLI flags
    cfg_dict: dict = {}
    if args.config:
        cfg_dict = _load_yaml_config(args.config)

    config = IdeaGeneratorConfig(
        model=args.model or cfg_dict.get("model", IdeaGeneratorConfig.model),
        max_generations=args.max_generations if args.max_generations is not None else cfg_dict.get("max_generations", IdeaGeneratorConfig.max_generations),
        num_reflections=args.num_reflections if args.num_reflections is not None else cfg_dict.get("num_reflections", IdeaGeneratorConfig.num_reflections),
        output_dir=cfg_dict.get("output_dir", IdeaGeneratorConfig.output_dir),
        validate=not args.no_validate and cfg_dict.get("validate", True),
        novelty_scoring=args.novelty_scoring or cfg_dict.get("novelty_scoring", False),
        novelty_model=args.novelty_model or cfg_dict.get("novelty_model", ""),
        checkpoint_interval=cfg_dict.get("checkpoint_interval", IdeaGeneratorConfig.checkpoint_interval),
        arxiv_enabled=not args.no_arxiv and cfg_dict.get("arxiv_enabled", True),
        resume=args.resume or cfg_dict.get("resume", False),
        system_prompt_override=cfg_dict.get("system_prompt_override", ""),
    )

    logger.info("Config: %s", config)

    ideas = generate_ideas(
        topic_path=args.topic_file,
        config=config,
        output_path=args.output,
    )

    logger.info("Done. Generated %d ideas total.", len(ideas))


if __name__ == "__main__":
    main()
