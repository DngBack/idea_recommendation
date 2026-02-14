"""
Command-line interface for the idea generator.
Usage:
    python -m idea_generator --topic-file topics/example_icbinb.md
    idea-generator --topic-file topics/example_icbinb.md   # if installed via pip
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Load .env from current directory so OPENAI_API_KEY etc. are set without manual export
load_dotenv()

from .core import IdeaGeneratorConfig, generate_ideas
from .expansion import expand_hypotheses
from .llm import AVAILABLE_LLMS, create_client
from . import research_pipeline

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
        default=None,
        help="Path to a Markdown file describing the research topic (required unless --expand-hypotheses with --from-idea-json).",
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
        "--pubmed",
        action="store_true",
        default=False,
        help="Enable the PubMed search tool.",
    )
    parser.add_argument(
        "--openalex",
        action="store_true",
        default=False,
        help="Enable the OpenAlex search tool.",
    )
    parser.add_argument(
        "--expand-hypotheses",
        action="store_true",
        default=False,
        help="Only run hypothesis expansion: output sub-hypotheses to a JSON file (do not run full idea generation).",
    )
    parser.add_argument(
        "--from-idea-json",
        type=str,
        default=None,
        help="Path to a single idea JSON file; use with --expand-hypotheses to expand from this idea instead of a topic file.",
    )
    parser.add_argument(
        "--max-sub-hypotheses",
        type=int,
        default=10,
        help="Max number of sub-hypotheses to generate when using --expand-hypotheses (default 10).",
    )
    # Research pipeline (4-phase)
    parser.add_argument(
        "--pipeline",
        action="store_true",
        default=False,
        help="Run the full 4-phase research pipeline (literature review -> hypotheses -> direction -> experiment plan).",
    )
    parser.add_argument(
        "--phase",
        type=str,
        default=None,
        choices=["literature_review", "hypotheses", "direction", "experiment_plan"],
        help="Run only one pipeline phase; use with --from-literature, --from-hypotheses, or --from-direction as needed.",
    )
    parser.add_argument(
        "--from-literature",
        type=str,
        default=None,
        help="Path to lit_review.json; required for --phase hypotheses, optional for --phase direction.",
    )
    parser.add_argument(
        "--from-hypotheses",
        type=str,
        default=None,
        help="Path to hypotheses.json; required for --phase direction.",
    )
    parser.add_argument(
        "--from-direction",
        type=str,
        default=None,
        help="Path to direction.json; required for --phase experiment_plan.",
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

    # ---------- Expansion-only mode ----------
    if args.expand_hypotheses:
        cfg_dict = _load_yaml_config(args.config) if args.config else {}
        if args.from_idea_json:
            idea_path = Path(args.from_idea_json).resolve()
            if not idea_path.exists():
                logger.error("Idea file not found: %s", idea_path)
                sys.exit(1)
            with open(idea_path, "r", encoding="utf-8") as f:
                idea_dict = json.load(f)
            if isinstance(idea_dict, list) and idea_dict:
                idea_dict = idea_dict[0]
            topic_text = None
            out_base = idea_path.stem
        else:
            if not args.topic_file:
                logger.error("--topic-file is required when using --expand-hypotheses without --from-idea-json.")
                sys.exit(1)
            topic_path = Path(args.topic_file).resolve()
            if not topic_path.exists():
                logger.error("Topic file not found: %s", topic_path)
                sys.exit(1)
            with open(topic_path, "r", encoding="utf-8") as f:
                topic_text = f.read()
            idea_dict = None
            out_base = topic_path.stem

        model = args.model or cfg_dict.get("model", IdeaGeneratorConfig.model)
        client, model = create_client(model)
        hypotheses = expand_hypotheses(
            topic_text=topic_text,
            idea_dict=idea_dict,
            client=client,
            model=model,
            max_sub=args.max_sub_hypotheses,
        )
        output_dir = cfg_dict.get("output_dir", "output")
        output_path = args.output or str(Path(output_dir) / f"{out_base}.hypotheses.json")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(hypotheses, f, indent=2, ensure_ascii=False)
        logger.info("Wrote %d sub-hypotheses to %s", len(hypotheses), output_path)
        return

    # ---------- Research pipeline (full or single phase) ----------
    cfg_dict = _load_yaml_config(args.config) if args.config else {}
    if args.pipeline or args.phase:
        rp_cfg = cfg_dict.get("research_pipeline") or {}
        config = IdeaGeneratorConfig(
            model=args.model or cfg_dict.get("model", IdeaGeneratorConfig.model),
            max_generations=cfg_dict.get("max_generations", IdeaGeneratorConfig.max_generations),
            num_reflections=cfg_dict.get("num_reflections", IdeaGeneratorConfig.num_reflections),
            output_dir=cfg_dict.get("output_dir", IdeaGeneratorConfig.output_dir),
            validate=not args.no_validate and cfg_dict.get("validate", True),
            novelty_scoring=args.novelty_scoring or cfg_dict.get("novelty_scoring", False),
            novelty_model=args.novelty_model or cfg_dict.get("novelty_model", ""),
            checkpoint_interval=cfg_dict.get("checkpoint_interval", IdeaGeneratorConfig.checkpoint_interval),
            arxiv_enabled=not args.no_arxiv and cfg_dict.get("arxiv_enabled", True),
            pubmed_enabled=args.pubmed or cfg_dict.get("pubmed_enabled", False),
            openalex_enabled=args.openalex or cfg_dict.get("openalex_enabled", False),
            resume=args.resume or cfg_dict.get("resume", False),
            system_prompt_override=cfg_dict.get("system_prompt_override", ""),
            pipeline_mode=True,
            pipeline_literature_reflections=rp_cfg.get("literature_reflections", IdeaGeneratorConfig.pipeline_literature_reflections),
            pipeline_direction_reflections=rp_cfg.get("direction_reflections", IdeaGeneratorConfig.pipeline_direction_reflections),
            pipeline_max_hypotheses=rp_cfg.get("max_hypotheses", IdeaGeneratorConfig.pipeline_max_hypotheses),
        )
        output_dir = config.output_dir
        if args.phase:
            if args.phase == "literature_review":
                if not args.topic_file:
                    logger.error("--topic-file is required for --phase literature_review.")
                    sys.exit(1)
                out_path = args.output or str(Path(output_dir) / f"{Path(args.topic_file).stem}.lit_review.json")
                research_pipeline.run_literature_review(args.topic_file, config, out_path)
                logger.info("Phase 1 complete: %s", out_path)
            elif args.phase == "hypotheses":
                from_lit = args.from_literature
                if not from_lit:
                    logger.error("--from-literature is required for --phase hypotheses.")
                    sys.exit(1)
                if not Path(from_lit).exists():
                    logger.error("File not found: %s", from_lit)
                    sys.exit(1)
                out_path = args.output or str(Path(output_dir) / f"{Path(from_lit).stem.replace('.lit_review', '')}.hypotheses.json")
                research_pipeline.run_gap_hypotheses(from_lit, config, out_path)
                logger.info("Phase 2 complete: %s", out_path)
            elif args.phase == "direction":
                from_hyp = args.from_hypotheses
                if not from_hyp:
                    logger.error("--from-hypotheses is required for --phase direction.")
                    sys.exit(1)
                if not Path(from_hyp).exists():
                    logger.error("File not found: %s", from_hyp)
                    sys.exit(1)
                from_lit = args.from_literature
                if not from_lit:
                    from_lit = str(Path(from_hyp).parent / (Path(from_hyp).stem.replace(".hypotheses", "") + ".lit_review.json"))
                if not Path(from_lit).exists():
                    logger.error("Literature review file not found: %s (use --from-literature to specify)", from_lit)
                    sys.exit(1)
                out_path = args.output or str(Path(output_dir) / f"{Path(from_hyp).stem.replace('.hypotheses', '')}.direction.json")
                research_pipeline.run_direction(from_lit, from_hyp, config, out_path)
                logger.info("Phase 3 complete: %s", out_path)
            else:
                from_dir = args.from_direction
                if not from_dir:
                    logger.error("--from-direction is required for --phase experiment_plan.")
                    sys.exit(1)
                if not Path(from_dir).exists():
                    logger.error("File not found: %s", from_dir)
                    sys.exit(1)
                out_path = args.output or str(Path(output_dir) / f"{Path(from_dir).stem.replace('.direction', '')}.experiment_plan.json")
                research_pipeline.run_experiment_plan(from_dir, config, out_path)
                logger.info("Phase 4 complete: %s", out_path)
        else:
            if not args.topic_file:
                logger.error("--topic-file is required for --pipeline.")
                sys.exit(1)
            paths = research_pipeline.run_full_research_pipeline(args.topic_file, config, output_dir)
            logger.info("Pipeline complete. Artifacts: %s", paths)
        return

    # ---------- Normal (legacy) idea generation ----------
    if not args.topic_file:
        logger.error("--topic-file is required for idea generation.")
        sys.exit(1)

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
        pubmed_enabled=args.pubmed or cfg_dict.get("pubmed_enabled", False),
        openalex_enabled=args.openalex or cfg_dict.get("openalex_enabled", False),
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
