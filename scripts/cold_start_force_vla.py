"""Cold start: ingest and compile ~25 Force-VLA papers into the wiki.

Usage:
    python3 -m scripts.cold_start_force_vla [--ingest-only] [--compile-only] [--batch N]

This script collects Force-VLA related papers across five research angles:
1. Force/torque sensing + manipulation learning
2. Contact-rich policy learning (diffusion, RL)
3. Tactile-vision fusion for manipulation
4. Impedance/compliance control + learning
5. VLA with force/tactile modality
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from scripts.config import get_wiki_path
from scripts.index_builder import build_all_indexes
from scripts.raw_ingest import ingest_batch
from scripts.wiki_compiler import compile_batch_v2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Force-VLA paper collection (~25 papers)
# ---------------------------------------------------------------------------

FORCE_VLA_PAPERS: list[dict] = [
    # --- Force-VLA / Force-aware policy (2025-2026 core) ---
    {"id": "2603.15169", "title": "ForceVLA2: Unleashing Hybrid Force-Position Control with Force Awareness"},
    {"id": "2505.22159", "title": "ForceVLA: Enhancing VLA Models with a Force-aware MoE for Contact-rich Manipulation"},
    {"id": "2602.22088", "title": "Force Policy: Learning Hybrid Force-Position Control Policy under Interaction Framework"},
    {"id": "2601.20321", "title": "TaF-VLA: Tactile-Force Alignment in Vision-Language-Action Models"},
    {"id": "2602.12532", "title": "CRAFT: Adapting VLA Models to Contact-rich Manipulation via Force-aware Curriculum"},
    {"id": "2602.01153", "title": "UniForce: A Unified Latent Force Model for Robot Manipulation with Diverse Tactile"},
    {"id": "2602.23648", "title": "FAVLA: A Force-Adaptive Fast-Slow VLA model for Contact-Rich Robotic Manipulation"},
    {"id": "2602.10013", "title": "Learning Force-Regulated Manipulation with a Low-Cost Tactile-Force-Controlled Gripper"},

    # --- Tactile-VLA fusion ---
    {"id": "2603.14604", "title": "Tactile Modality Fusion for Vision-Language-Action Models"},
    {"id": "2603.12665", "title": "TacVLA: Contact-Aware Tactile Fusion for Robust Vision-Language-Action Manipulation"},
    {"id": "2507.09160", "title": "Tactile-VLA: Unlocking Vision-Language-Action Model's Physical Knowledge"},
    {"id": "2508.08706", "title": "OmniVTLA: Vision-Tactile-Language-Action Model with Semantic-Aligned Tactile Sensing"},
    {"id": "2512.23864", "title": "Learning to Feel the Future: DreamTacVLA for Contact-Rich Manipulation"},
    {"id": "2503.08548", "title": "TLA: Tactile-Language-Action Model for Contact-Rich Manipulation"},
    {"id": "2603.15257", "title": "HapticVLA: Contact-Rich Manipulation via VLA Model without Instrumented Objects"},

    # --- Force-aware reactive policy ---
    {"id": "2411.15753", "title": "FoAR: Force-Aware Reactive Policy for Contact-Rich Robotic Manipulation"},
    {"id": "2603.04038", "title": "Force-Aware Residual DAgger via Trajectory Editing for Precision Insertion"},
    {"id": "2603.08342", "title": "PhaForce: Phase-Scheduled Visual-Force Policy with Slow Planning and Fast Control"},
    {"id": "2503.02881", "title": "Reactive Diffusion Policy: Slow-Fast Visual-Tactile Policy for Contact-Rich Manipulation"},
    {"id": "2602.14174", "title": "Direction Matters: Learning Force Direction Enables Sim-to-Real Contact-Rich Manipulation"},
    {"id": "2510.13324", "title": "Tactile-Conditioned Diffusion Policy for Force-Aware Robotic Manipulation"},
    {"id": "2410.07554", "title": "ForceMimic: Force-Centric Imitation Learning with Force-Motion Capture System"},

    # --- Impedance/compliance + learning ---
    {"id": "2509.19696", "title": "Diffusion-Based Impedance Learning for Contact-Rich Manipulation Tasks"},
    {"id": "2509.17053", "title": "FILIC: Dual-Loop Force-Guided Imitation Learning with Impedance Torque Control"},
    {"id": "2502.17432", "title": "FACTR: Force-Attending Curriculum Training for Contact-Rich Policy Learning"},
    {"id": "2410.09309", "title": "Adaptive Compliance Policy: Learning Approximate Compliance for Diffusion Guided Manipulation"},

    # --- Force prediction / force-guided planning ---
    {"id": "2409.11047", "title": "TacDiffusion: Force-domain Diffusion Policy for Precise Tactile Manipulation"},
    {"id": "2505.13982", "title": "Adaptive Visuo-Tactile Fusion with Predictive Force Attention for Dexterous Manipulation"},
    {"id": "2604.01414", "title": "Learning When to See and When to Feel: Adaptive Vision-Torque Fusion"},
]


def run_cold_start(
    wiki_dir: Path | None = None,
    *,
    ingest_only: bool = False,
    compile_only: bool = False,
    batch_size: int = 5,
) -> dict:
    """Run the Force-VLA cold start pipeline.

    Steps:
    1. ingest_batch() — network I/O only (arXiv + S2 + fulltext)
    2. compile_batch_v2() — LLM calls (2 per paper)
    3. build_all_indexes() — rebuild all wiki indexes
    """
    resolved = wiki_dir if wiki_dir is not None else get_wiki_path()
    arxiv_ids = [p["id"] for p in FORCE_VLA_PAPERS]
    result = {"ingested": 0, "skipped": 0, "failed": [], "compiled": 0}

    # Step 1: Ingest
    if not compile_only:
        logger.info("=== Step 1: Ingesting %d papers ===", len(arxiv_ids))
        ingest_result = ingest_batch(arxiv_ids, resolved, delay=1.5)
        result["ingested"] = ingest_result["ingested"]
        result["skipped"] = ingest_result["skipped"]
        result["failed"] = ingest_result["failed"]
        logger.info(
            "Ingest complete: %d ingested, %d skipped, %d failed",
            ingest_result["ingested"],
            ingest_result["skipped"],
            len(ingest_result["failed"]),
        )

        if ingest_only:
            return result

    # Step 2: Compile in batches
    if not ingest_only:
        # Filter to only IDs that have raw data
        compilable = []
        for aid in arxiv_ids:
            meta_path = resolved / "raw" / "papers" / aid / "meta.yaml"
            if meta_path.exists():
                compilable.append(aid)
            else:
                logger.warning("No raw data for %s, skipping compilation", aid)

        logger.info("=== Step 2: Compiling %d papers (batch_size=%d) ===", len(compilable), batch_size)
        compile_result = compile_batch_v2(compilable, resolved, max_papers=batch_size)
        result["compiled"] = compile_result["papers_compiled"]
        logger.info(
            "Compile complete: %d compiled, %d failed",
            compile_result["papers_compiled"],
            len(compile_result.get("failed", [])),
        )

    # Step 3: Build indexes
    logger.info("=== Step 3: Building indexes ===")
    build_all_indexes(resolved)
    logger.info("Indexes rebuilt")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Cold start Force-VLA wiki")
    parser.add_argument("--ingest-only", action="store_true", help="Only ingest raw data, skip compilation")
    parser.add_argument("--compile-only", action="store_true", help="Only compile (assumes raw data exists)")
    parser.add_argument("--batch", type=int, default=5, help="Batch size for compilation (default: 5)")
    args = parser.parse_args()

    result = run_cold_start(
        ingest_only=args.ingest_only,
        compile_only=args.compile_only,
        batch_size=args.batch,
    )

    logger.info("Cold start result: %s", result)


if __name__ == "__main__":
    main()
