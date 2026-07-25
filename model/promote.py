"""Promote only six-output, realized Heat/Rain model artifacts."""

from __future__ import annotations

import argparse
import logging
import math
import os
import re
import sys

import mlflow.sklearn
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
    validate_fitted_pipeline,
)
from model.extract_data import (
    CANONICAL_VINTAGE_RULE,
    LABEL_SOURCE,
    SUPPORTED_TARGET_COMPONENTS,
    UNSUPPORTED_TARGET_COMPONENTS,
)
from model.rule_baselines import (
    RULE_BASELINE_CONTRACT,
    RULE_BASELINE_SCORE_NAMES,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

MIN_COMPONENT_R2 = 0.0
MIN_RULE_MAE_IMPROVEMENT = 0.05
HEAT_MAE_THRESHOLDS_BY_HORIZON = {
    1: 10.0,
    2: 11.0,
    3: 12.0,
}
RAIN_MAE_THRESHOLD = 7.0
SCORE_NAMES = RULE_BASELINE_SCORE_NAMES

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
    "model_role": "challenger",
    "forecast_horizons": ",".join(map(str, FORECAST_HORIZONS)),
    "target_score_names": ",".join(TARGET_SCORE_NAMES),
    "target_columns": ",".join(TARGET_COLUMNS),
    "output_count": str(len(TARGET_COLUMNS)),
    "label_source": LABEL_SOURCE,
    "supported_target_components": SUPPORTED_TARGET_COMPONENTS,
    "unsupported_target_components": UNSUPPORTED_TARGET_COMPONENTS,
    "canonical_vintage_rule": CANONICAL_VINTAGE_RULE,
    "rule_baseline_contract": RULE_BASELINE_CONTRACT,
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
    """Return fatal artifact/training-contract failures.

    Minimum held-out support is evaluated separately as a quality decision so
    staging may retain the rule-based champion when a challenger is merely
    under-supported. Missing or internally inconsistent provenance remains a
    hard execution failure, including in ``--allow-rejected`` mode.
    """
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
    return failures


def _dataset_support_failures(params: dict[str, str]) -> list[str]:
    """Return non-promotable held-out dataset support failures."""

    failures = []
    test_rows = _positive_int_param(params, "test_rows")
    test_dates = _positive_int_param(params, "test_distinct_origin_dates")
    if test_rows is not None and test_rows < MIN_TEST_ROWS:
        failures.append(f"test_rows {test_rows} is below minimum {MIN_TEST_ROWS}")
    if test_dates is not None and test_dates < MIN_TEST_ORIGIN_DATES:
        failures.append(
            f"test_distinct_origin_dates {test_dates} is below minimum "
            f"{MIN_TEST_ORIGIN_DATES}"
        )
    return failures


def _metric_contract_failures(
    metrics: dict[str, float],
    test_rows: int,
) -> list[str]:
    """Validate that candidate and rule metrics cover identical held-out rows."""

    failures = []
    for horizon in FORECAST_HORIZONS:
        horizon_r2 = _finite_metric(metrics, f"r2_d{horizon}")
        horizon_mae = _finite_metric(metrics, f"mae_d{horizon}")
        # Aggregate metrics are diagnostics only. Their absence or value does
        # not decide promotion; report them when the training run provided both.
        if horizon_r2 is not None and horizon_mae is not None:
            logging.info(
                "Day +%s aggregate diagnostics -> R2: %.4f, MAE: %.4f",
                horizon,
                horizon_r2,
                horizon_mae,
            )

        for score_name in SCORE_NAMES:
            required_metric_names = (
                f"r2_{score_name}_d{horizon}",
                f"mae_{score_name}_d{horizon}",
                f"rule_r2_{score_name}_d{horizon}",
                f"rule_mae_{score_name}_d{horizon}",
                f"test_count_{score_name}_d{horizon}",
                f"rule_test_count_{score_name}_d{horizon}",
                f"test_std_{score_name}_d{horizon}",
                f"test_nonzero_count_{score_name}_d{horizon}",
            )
            parsed_metrics = {
                name: _finite_metric(metrics, name)
                for name in required_metric_names
            }
            missing_metrics = [
                name for name, value in parsed_metrics.items() if value is None
            ]
            if missing_metrics:
                failures.append(
                    f"Day +{horizon} {score_name} finite evaluation metrics are "
                    "missing: " + ", ".join(missing_metrics)
                )
                continue

            support_count = parsed_metrics[f"test_count_{score_name}_d{horizon}"]
            rule_support_count = parsed_metrics[
                f"rule_test_count_{score_name}_d{horizon}"
            ]
            nonzero_count = parsed_metrics[
                f"test_nonzero_count_{score_name}_d{horizon}"
            ]
            assert support_count is not None
            assert rule_support_count is not None
            assert nonzero_count is not None
            if not support_count.is_integer() or int(support_count) != test_rows:
                failures.append(
                    f"Day +{horizon} {score_name} candidate support must equal "
                    f"test_rows {test_rows}; found {support_count}"
                )
            if (
                not rule_support_count.is_integer()
                or int(rule_support_count) != test_rows
            ):
                failures.append(
                    f"Day +{horizon} {score_name} rule support must equal "
                    f"test_rows {test_rows}; found {rule_support_count}"
                )
            if not nonzero_count.is_integer() or not 0 <= nonzero_count <= test_rows:
                failures.append(
                    f"Day +{horizon} {score_name} non-zero target support is "
                    "inconsistent"
                )
    return failures


def _quality_failures(
    metrics: dict[str, float],
    test_rows: int,
) -> list[str]:
    """Decide whether the challenger is demonstrably better than its rules."""

    failures = []
    for horizon in FORECAST_HORIZONS:
        for score_name in SCORE_NAMES:
            component_r2 = float(metrics[f"r2_{score_name}_d{horizon}"])
            component_mae = float(metrics[f"mae_{score_name}_d{horizon}"])
            rule_r2 = float(metrics[f"rule_r2_{score_name}_d{horizon}"])
            rule_mae = float(metrics[f"rule_mae_{score_name}_d{horizon}"])
            support_count = float(
                metrics[f"test_count_{score_name}_d{horizon}"]
            )
            support_std = float(metrics[f"test_std_{score_name}_d{horizon}"])
            nonzero_count = float(
                metrics[f"test_nonzero_count_{score_name}_d{horizon}"]
            )

            logging.info(
                "Day +%s %s challenger -> R2: %.4f, MAE: %.4f; "
                "same-vintage rule -> R2: %.4f, MAE: %.4f",
                horizon,
                score_name,
                component_r2,
                component_mae,
                rule_r2,
                rule_mae,
            )
            if component_r2 < MIN_COMPONENT_R2:
                failures.append(
                    f"Day +{horizon} {score_name} R2 {component_r2:.4f} is negative"
                )
            if score_name == "heat_score":
                mae_limit = HEAT_MAE_THRESHOLDS_BY_HORIZON[horizon]
            else:
                mae_limit = RAIN_MAE_THRESHOLD
            if component_mae > mae_limit:
                failures.append(
                    f"Day +{horizon} {score_name} MAE {component_mae:.4f} "
                    f"> secondary ceiling {mae_limit:.1f}"
                )

            if rule_mae <= 0.0:
                failures.append(
                    f"Day +{horizon} {score_name} cannot beat a perfect "
                    "same-vintage rule baseline"
                )
            else:
                required_mae = rule_mae * (1.0 - MIN_RULE_MAE_IMPROVEMENT)
                if component_mae > required_mae:
                    failures.append(
                        f"Day +{horizon} {score_name} MAE {component_mae:.4f} "
                        f"does not beat rule MAE {rule_mae:.4f} by at least "
                        f"{MIN_RULE_MAE_IMPROVEMENT:.0%} (required <= "
                        f"{required_mae:.4f})"
                    )

            if support_count < MIN_TARGET_TEST_COUNT:
                failures.append(
                    f"Day +{horizon} {score_name} support is below "
                    f"{MIN_TARGET_TEST_COUNT}"
                )
            if support_std <= MIN_TARGET_STD:
                failures.append(
                    f"Day +{horizon} {score_name} target variation is insufficient"
                )
            if nonzero_count < MIN_TARGET_NONZERO_COUNT:
                failures.append(
                    f"Day +{horizon} {score_name} non-zero target support is "
                    "insufficient"
                )
    return failures


def _write_promotion_output(promoted: bool, version: str) -> None:
    github_output = os.environ.get("GITHUB_OUTPUT")
    if not github_output:
        return
    with open(github_output, "a", encoding="utf-8") as output_file:
        output_file.write(f"model_promoted={'true' if promoted else 'false'}\n")
        output_file.write(f"candidate_model_version={version}\n")


def _load_and_validate_candidate_artifact(version: str):
    """Load the exact registry version and verify its fitted semantic contract."""

    model_uri = f"models:/{REGISTERED_MODEL_NAME}/{version}"
    estimator = mlflow.sklearn.load_model(model_uri)
    validate_fitted_pipeline(estimator)
    return estimator


def promote_model(*, allow_rejected: bool = False) -> bool:
    """Evaluate and conditionally promote the exact training-job version.

    When ``allow_rejected`` is true, an otherwise valid challenger that misses
    quality or support gates is retained in MLflow and returns ``False`` without
    failing the process. Authentication, registry, runtime, and artifact/data
    contract errors always remain fatal.
    """
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
        _load_and_validate_candidate_artifact(str(candidate_version.version))
        logging.info(
            "Evaluating Model '%s' (Version %s, Run ID: %s)",
            REGISTERED_MODEL_NAME,
            candidate_version.version,
            run_id,
        )
        run = client.get_run(run_id)
        params = run.data.params
        metrics = run.data.metrics

        contract_failures = _metadata_failures(params)
        test_rows = _positive_int_param(params, "test_rows")
        if test_rows is not None:
            contract_failures.extend(_metric_contract_failures(metrics, test_rows))

        if contract_failures:
            logging.error(
                "❌ Candidate evaluation contract is invalid:\n - %s",
                "\n - ".join(contract_failures),
            )
            sys.exit(1)

        assert test_rows is not None
        failed_gates = _dataset_support_failures(params)
        failed_gates.extend(_quality_failures(metrics, test_rows))
        if failed_gates:
            logging.error(
                "❌ Challenger quality gates failed; model was NOT promoted:\n - %s",
                "\n - ".join(failed_gates),
            )
            _write_promotion_output(False, str(candidate_version.version))
            if allow_rejected:
                logging.info(
                    "Rejected challenger retained for analysis; continuing because "
                    "--allow-rejected was specified."
                )
                return False
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
        _write_promotion_output(True, str(candidate_version.version))
        return True
    except Exception as exc:
        logging.error("An error occurred during promotion evaluation: %s", exc)
        sys.exit(1)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate a Heat/Rain challenger against same-vintage rules."
    )
    parser.add_argument(
        "--allow-rejected",
        action="store_true",
        help=(
            "Return success for quality-gate rejection while leaving the "
            "candidate unpromoted; contract and runtime failures remain fatal."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args()
    promote_model(allow_rejected=arguments.allow_rejected)
