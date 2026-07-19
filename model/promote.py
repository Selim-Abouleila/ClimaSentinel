"""Promote only six-output, realized Heat/Rain model artifacts."""

from __future__ import annotations

import logging
import math
import os
import re
import sys

from mlflow.tracking import MlflowClient

from backend.app.ml_pipeline import (
    FEATURE_SCHEMA_VERSION,
    FORECAST_HORIZONS,
    MAX_LABEL_LOOKAHEAD_DAYS,
    REGISTERED_MODEL_NAME,
    TARGET_COLUMNS,
    TARGET_SCHEMA_VERSION,
    TARGET_SCORE_NAMES,
    TRAINING_DATA_CONTRACT,
)
from model.extract_data import (
    CANONICAL_VINTAGE_RULE,
    LABEL_SOURCE,
    SUPPORTED_TARGET_COMPONENTS,
    UNSUPPORTED_TARGET_COMPONENTS,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

R2_THRESHOLD = 0.35
HORIZON_MAE_THRESHOLD = 7.0
COMPONENT_MAE_THRESHOLDS = {
    "heat_score": 10.0,
    "rain_score": 7.0,
}
SCORE_NAMES = tuple(COMPONENT_MAE_THRESHOLDS)

# Promotion requires enough genuinely held-out evidence to make R2 meaningful.
MIN_TEST_ROWS = 50
MIN_TEST_ORIGIN_DATES = 8
MIN_TARGET_TEST_COUNT = 50
MIN_TARGET_NONZERO_COUNT = 5
MIN_TARGET_STD = 1e-6

EXPECTED_PARAMS = {
    "feature_schema_version": FEATURE_SCHEMA_VERSION,
    "target_schema_version": TARGET_SCHEMA_VERSION,
    "training_data_contract": TRAINING_DATA_CONTRACT,
    "registered_model_name": REGISTERED_MODEL_NAME,
    "forecast_horizons": ",".join(map(str, FORECAST_HORIZONS)),
    "target_score_names": ",".join(TARGET_SCORE_NAMES),
    "target_columns": ",".join(TARGET_COLUMNS),
    "output_count": str(len(TARGET_COLUMNS)),
    "label_source": LABEL_SOURCE,
    "supported_target_components": SUPPORTED_TARGET_COMPONENTS,
    "unsupported_target_components": UNSUPPORTED_TARGET_COMPONENTS,
    "canonical_vintage_rule": CANONICAL_VINTAGE_RULE,
    "training_grain": "city_id,forecast_origin_date",
    "purge_gap_days": str(MAX_LABEL_LOOKAHEAD_DAYS),
}


def _finite_metric(metrics: dict[str, float], name: str) -> float | None:
    value = metrics.get(name)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_int_param(params: dict[str, str], name: str) -> int | None:
    value = params.get(name)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _metadata_failures(params: dict[str, str]) -> list[str]:
    failures = []
    for name, expected in EXPECTED_PARAMS.items():
        actual = params.get(name)
        if actual != expected:
            failures.append(
                f"parameter {name}={actual!r}; expected {expected!r}"
            )

    git_commit = params.get("git_commit", "")
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", git_commit):
        failures.append("git_commit is missing or is not a Git object ID")
    dvc_hash = params.get("dvc_data_hash", "")
    if not re.fullmatch(r"[0-9a-fA-F]{32}", dvc_hash):
        failures.append("dvc_data_hash is missing, unknown, or not an MD5 hash")

    row_count = _positive_int_param(params, "row_count")
    train_rows = _positive_int_param(params, "train_rows")
    test_rows = _positive_int_param(params, "test_rows")
    distinct_dates = _positive_int_param(params, "distinct_origin_dates")
    train_dates = _positive_int_param(params, "train_distinct_origin_dates")
    test_dates = _positive_int_param(params, "test_distinct_origin_dates")
    if None in (
        row_count,
        train_rows,
        test_rows,
        distinct_dates,
        train_dates,
        test_dates,
    ):
        failures.append("training split row/date provenance parameters are incomplete")
    else:
        assert row_count is not None
        assert train_rows is not None
        assert test_rows is not None
        assert distinct_dates is not None
        assert train_dates is not None
        assert test_dates is not None
        if train_rows + test_rows >= row_count:
            failures.append(
                "purged split provenance must account for at least one excluded row"
            )
        if train_dates + test_dates >= distinct_dates:
            failures.append(
                "purged split provenance must account for excluded origin dates"
            )
        if test_rows < MIN_TEST_ROWS:
            failures.append(
                f"test_rows {test_rows} is below minimum {MIN_TEST_ROWS}"
            )
        if test_dates < MIN_TEST_ORIGIN_DATES:
            failures.append(
                f"test_distinct_origin_dates {test_dates} is below minimum "
                f"{MIN_TEST_ORIGIN_DATES}"
            )
    return failures


def _quality_failures(
    metrics: dict[str, float],
    test_rows: int,
) -> list[str]:
    failures = []
    for horizon in FORECAST_HORIZONS:
        horizon_r2 = _finite_metric(metrics, f"r2_d{horizon}")
        horizon_mae = _finite_metric(metrics, f"mae_d{horizon}")
        if horizon_r2 is None or horizon_mae is None:
            failures.append(f"Day +{horizon} finite aggregate metrics are missing")
        else:
            logging.info(
                "Day +%s metrics -> R2: %.4f, MAE: %.4f",
                horizon,
                horizon_r2,
                horizon_mae,
            )
            if horizon_r2 < R2_THRESHOLD:
                failures.append(
                    f"Day +{horizon} R2 {horizon_r2:.4f} < {R2_THRESHOLD:.2f}"
                )
            if horizon_mae > HORIZON_MAE_THRESHOLD:
                failures.append(
                    f"Day +{horizon} MAE {horizon_mae:.4f} > "
                    f"{HORIZON_MAE_THRESHOLD:.1f}"
                )

        for score_name in SCORE_NAMES:
            component_r2 = _finite_metric(
                metrics, f"r2_{score_name}_d{horizon}"
            )
            component_mae = _finite_metric(
                metrics, f"mae_{score_name}_d{horizon}"
            )
            support_count = _finite_metric(
                metrics, f"test_count_{score_name}_d{horizon}"
            )
            support_std = _finite_metric(
                metrics, f"test_std_{score_name}_d{horizon}"
            )
            nonzero_count = _finite_metric(
                metrics, f"test_nonzero_count_{score_name}_d{horizon}"
            )
            if component_r2 is None or component_mae is None:
                failures.append(
                    f"Day +{horizon} {score_name} finite metrics are missing"
                )
                continue
            logging.info(
                "Day +%s %s -> R2: %.4f, MAE: %.4f",
                horizon,
                score_name,
                component_r2,
                component_mae,
            )
            if component_r2 < R2_THRESHOLD:
                failures.append(
                    f"Day +{horizon} {score_name} R2 {component_r2:.4f} "
                    f"< {R2_THRESHOLD:.2f}"
                )
            mae_limit = COMPONENT_MAE_THRESHOLDS[score_name]
            if component_mae > mae_limit:
                failures.append(
                    f"Day +{horizon} {score_name} MAE {component_mae:.4f} "
                    f"> {mae_limit:.1f}"
                )
            if support_count is None or not support_count.is_integer():
                failures.append(
                    f"Day +{horizon} {score_name} test support is missing"
                )
            elif int(support_count) != test_rows:
                failures.append(
                    f"Day +{horizon} {score_name} support {int(support_count)} "
                    f"does not equal test_rows {test_rows}"
                )
            elif support_count < MIN_TARGET_TEST_COUNT:
                failures.append(
                    f"Day +{horizon} {score_name} support is below "
                    f"{MIN_TARGET_TEST_COUNT}"
                )
            if support_std is None or support_std <= MIN_TARGET_STD:
                failures.append(
                    f"Day +{horizon} {score_name} target variation is insufficient"
                )
            if (
                nonzero_count is None
                or not nonzero_count.is_integer()
                or nonzero_count < MIN_TARGET_NONZERO_COUNT
                or nonzero_count > test_rows
            ):
                failures.append(
                    f"Day +{horizon} {score_name} non-zero target support is "
                    "insufficient or inconsistent"
                )
    return failures


def promote_model() -> None:
    """Evaluate and promote the exact version emitted by the training job."""
    dagshub_username = os.environ.get(
        "DAGSHUB_USERNAME", "Selim-Abouleila"
    ).strip()
    dagshub_token = os.environ.get("DAGSHUB_USER_TOKEN", "").strip()
    if not dagshub_token:
        logging.error("Missing DAGSHUB_USER_TOKEN environment variable.")
        sys.exit(1)

    try:
        import dagshub

        dagshub.init(
            repo_owner=dagshub_username,
            repo_name="ClimaSentinel",
            mlflow=True,
        )
    except Exception as exc:
        logging.error("Failed to initialize DagsHub: %s", exc)
        sys.exit(1)

    client = MlflowClient()
    model_alias = os.environ.get("MLFLOW_MODEL_ALIAS", "champion").strip() or "champion"
    configured_version = os.environ.get("MLFLOW_MODEL_VERSION", "").strip()

    try:
        if configured_version:
            if not configured_version.isdigit() or int(configured_version) <= 0:
                logging.error("MLFLOW_MODEL_VERSION must be a positive integer.")
                sys.exit(1)
            candidate_version = client.get_model_version(
                REGISTERED_MODEL_NAME,
                str(int(configured_version)),
            )
        else:
            versions = client.search_model_versions(
                f"name='{REGISTERED_MODEL_NAME}'"
            )
            if not versions:
                logging.error(
                    "No versions found for model '%s'.", REGISTERED_MODEL_NAME
                )
                sys.exit(1)
            candidate_version = max(
                versions,
                key=lambda version: int(version.version),
            )

        run_id = candidate_version.run_id
        candidate_status = str(getattr(candidate_version, "status", "")).upper()
        if candidate_status.split(".")[-1] != "READY":
            logging.error(
                "Candidate model version %s is not READY (status=%r).",
                candidate_version.version,
                getattr(candidate_version, "status", None),
            )
            sys.exit(1)
        logging.info(
            "Evaluating Model '%s' (Version %s, Run ID: %s)",
            REGISTERED_MODEL_NAME,
            candidate_version.version,
            run_id,
        )
        run = client.get_run(run_id)
        params = run.data.params
        metrics = run.data.metrics

        failed_gates = _metadata_failures(params)
        test_rows = _positive_int_param(params, "test_rows")
        if test_rows is not None:
            failed_gates.extend(_quality_failures(metrics, test_rows))

        if failed_gates:
            logging.error(
                "❌ Quality gates failed:\n - %s",
                "\n - ".join(failed_gates),
            )
            sys.exit(1)

        logging.info("✅ Quality and provenance gates passed.")
        client.transition_model_version_stage(
            name=REGISTERED_MODEL_NAME,
            version=candidate_version.version,
            stage="Production",
            archive_existing_versions=True,
        )
        client.set_registered_model_alias(
            REGISTERED_MODEL_NAME,
            model_alias,
            candidate_version.version,
        )
        logging.info(
            "Assigned alias '%s' to model version %s.",
            model_alias,
            candidate_version.version,
        )
        logging.info("Model successfully promoted to Production.")
    except Exception as exc:
        logging.error("An error occurred during promotion evaluation: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    promote_model()
