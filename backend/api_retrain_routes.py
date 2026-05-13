"""
Admin API endpoints for the retraining pipeline.
Provides manual trigger, status query, and rollback.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from pipeline import config
from pipeline.versioning import ModelRegistry
from pipeline.deployment import ModelDeployer
from pipeline_runner import run_pipeline, rollback

logger = logging.getLogger(__name__)

retrain_bp = Blueprint('retrain', __name__, url_prefix='/api/admin')


def _is_admin() -> bool:
    """Check if current user is admin. Must be called inside request context."""
    from database import get_user_by_id
    try:
        uid = int(get_jwt_identity())
        user = get_user_by_id(uid)
        return user is not None and user.role == 'admin'
    except Exception:
        return False


@retrain_bp.route('/retrain', methods=['POST'])
@jwt_required()
def admin_retrain():
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403

    data = request.get_json() or {}
    mode = data.get('mode', 'incremental')
    epochs = data.get('epochs')
    batch_size = data.get('batch_size')
    lr = data.get('learning_rate')
    min_feedback = data.get('min_feedback')
    dry_run = data.get('dry_run', False)

    logger.info(f"Admin triggered retrain: mode={mode}, dry_run={dry_run}")

    try:
        result = run_pipeline(
            mode=mode,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=lr,
            min_feedback=min_feedback,
            dry_run=dry_run
        )
        return jsonify({
            'success': result.get('success', False),
            'deployed': result.get('deployed', False),
            'run_id': result.get('run_id'),
            'evaluation': result.get('evaluation'),
            'training': {k: v for k, v in (result.get('training') or {}).items() if k != 'history'},
        })
    except Exception as e:
        logger.exception("Admin retrain failed")
        return jsonify({'success': False, 'error': str(e)}), 500


@retrain_bp.route('/retrain/status', methods=['GET'])
@jwt_required()
def retrain_status():
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403

    registry = ModelRegistry()
    champion = registry.get_champion()
    versions = registry.list_versions()

    # Read latest log if available
    latest_log = None
    log_dir = Path(config.RETRAIN_LOG_DIR)
    if log_dir.exists():
        logs = sorted(log_dir.glob('retrain_*.jsonl'), reverse=True)
        if logs:
            try:
                with open(logs[0], 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        latest_log = json.loads(lines[-1])
            except Exception:
                pass

    return jsonify({
        'success': True,
        'champion': champion,
        'total_versions': len(versions),
        'versions': [{'version_id': v['version_id'], 'status': v['status'], 'created_at': v.get('created_at')} for v in versions],
        'latest_log_event': latest_log,
    })


@retrain_bp.route('/retrain/rollback', methods=['POST'])
@jwt_required()
def admin_rollback():
    if not _is_admin():
        return jsonify({'success': False, 'message': 'Admin access required.'}), 403

    ok = rollback()
    if ok:
        return jsonify({'success': True, 'message': 'Rolled back to previous champion.'})
    return jsonify({'success': False, 'message': 'Rollback failed. No previous champion found.'}), 500
