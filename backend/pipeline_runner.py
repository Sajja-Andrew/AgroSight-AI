"""
Pipeline Runner — CLI and programmatic entrypoint for the full
feedback retraining pipeline.

Usage:
    python pipeline_runner.py --mode incremental --epochs 10 --min-feedback 5
    python pipeline_runner.py --mode full --epochs 30
    python pipeline_runner.py --rollback
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure backend is on path
backend_dir = Path(__file__).parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from pipeline import config
from pipeline.ingestion import FeedbackIngestion
from pipeline.validation import FeedbackValidator
from pipeline.preprocessing import DatasetBuilder
from pipeline.training import FeedbackRetrainer
from pipeline.evaluation import ModelEvaluator
from pipeline.versioning import ModelRegistry
from pipeline.deployment import ModelDeployer
from pipeline.monitoring import PipelineLogger
from pipeline.alerting import AlertManager

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def run_pipeline(mode: str = 'incremental',
                 epochs: int = None,
                 batch_size: int = None,
                 learning_rate: float = None,
                 min_feedback: int = None,
                 use_original_data: bool = True,
                 dry_run: bool = False) -> dict:
    """
    Orchestrate the complete retraining pipeline.
    Returns a summary dict.
    """
    min_feedback = min_feedback if min_feedback is not None else config.MIN_FEEDBACK_COUNT
    run_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    logger.info("=" * 60)
    logger.info("Feedback Retraining Pipeline Started")
    logger.info("=" * 60)

    pl = PipelineLogger()
    pl.start_run(run_id)
    result = {'run_id': run_id, 'success': False, 'deployed': False}

    try:
        # 1. Ingestion
        logger.info("[1/7] Ingesting feedback...")
        ingestion = FeedbackIngestion()
        entries = ingestion.ingest_all()
        pl.log_stage('ingestion', {'count': len(entries)})

        # 2. Validation
        logger.info("[2/7] Validating feedback...")
        validator = FeedbackValidator()
        clean_entries, stats = validator.validate(entries)
        pl.log_stage('validation', stats)
        result['validation_stats'] = stats

        if len(clean_entries) < min_feedback:
            AlertManager.alert_insufficient_feedback(len(clean_entries), min_feedback)
            logger.warning(f"Not enough feedback ({len(clean_entries)} < {min_feedback}). Aborting.")
            pl.end_run(status='aborted', error='insufficient_feedback')
            return result

        pl.log_feedback_distribution(clean_entries)

        # 3. Preprocessing
        logger.info("[3/7] Building dataset...")
        builder = DatasetBuilder()
        train_dir, val_dir = builder.build(clean_entries, use_original=use_original_data)
        _, _, train_data, val_data = builder.get_data_generators(train_dir, val_dir, batch_size)
        pl.log_stage('preprocessing', builder.get_manifest())
        result['dataset_manifest'] = builder.get_manifest()

        # 4. Training
        logger.info("[4/7] Training model...")
        retrainer = FeedbackRetrainer(
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate
        )
        train_info = retrainer.retrain(train_data, val_data, mode=mode)
        pl.log_stage('training', train_info)
        result['training'] = train_info

        # 5. Evaluation
        logger.info("[5/7] Evaluating model...")
        evaluator = ModelEvaluator(val_dir, batch_size=batch_size)
        comparison, should_promote = evaluator.compare(
            challenger_path=Path(train_info['model_path'])
        )
        pl.log_metrics(comparison)
        result['evaluation'] = comparison

        # 6. Versioning + Deployment
        logger.info("[6/7] Versioning & deployment...")
        registry = ModelRegistry()
        version_id = f"v{train_info['timestamp']}"
        registry.register(
            version_id=version_id,
            model_path=Path(train_info['model_path']),
            metrics=comparison['challenger'],
            status='challenger'
        )

        if should_promote and not dry_run:
            deployer = ModelDeployer(registry=registry)
            deployed = deployer.deploy(Path(train_info['model_path']), version_id)
            if deployed:
                pl.log_decision('deploy', f'Promoted {version_id}', {'metrics': comparison['challenger']})
                result['deployed'] = True
                result['active_version'] = version_id
                logger.info(f"✅ Deployed new champion: {version_id}")
            else:
                pl.log_decision('deploy_failed', 'Deployment step failed', {})
                logger.error("❌ Deployment failed")
        elif dry_run:
            pl.log_decision('dry_run', 'Promotion skipped (dry-run mode)', {})
            logger.info("Dry-run: model trained but not deployed")
        else:
            pl.log_decision('no_promote', 'Challenger did not meet improvement threshold', comparison)
            logger.info("Challenger did not improve enough; keeping current champion")

        result['success'] = True
        pl.end_run(status='completed')
        logger.info("=" * 60)
        logger.info("Pipeline completed successfully")
        logger.info("=" * 60)
        return result

    except Exception as e:
        logger.exception("Pipeline failed")
        AlertManager.alert_pipeline_failure(str(e))
        pl.end_run(status='failed', error=str(e))
        result['error'] = str(e)
        return result


def rollback() -> bool:
    logger.info("Initiating rollback...")
    deployer = ModelDeployer()
    ok = deployer.rollback()
    if ok:
        logger.info("Rollback successful")
    else:
        logger.error("Rollback failed")
    return ok


def main():
    parser = argparse.ArgumentParser(description='Smart Crop AI Feedback Retraining Pipeline')
    parser.add_argument('--mode', type=str, default='incremental', choices=['incremental', 'full'])
    parser.add_argument('--epochs', type=int, default=None)
    parser.add_argument('--batch-size', type=int, default=None)
    parser.add_argument('--lr', type=float, default=None)
    parser.add_argument('--min-feedback', type=int, default=None)
    parser.add_argument('--feedback-only', action='store_true', help='Do not include original training data')
    parser.add_argument('--dry-run', action='store_true', help='Train and evaluate but do not deploy')
    parser.add_argument('--rollback', action='store_true', help='Roll back to previous champion')

    args = parser.parse_args()

    if args.rollback:
        success = rollback()
        sys.exit(0 if success else 1)

    result = run_pipeline(
        mode=args.mode,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        min_feedback=args.min_feedback,
        use_original_data=not args.feedback_only,
        dry_run=args.dry_run
    )

    if not result['success']:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
