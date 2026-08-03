"""Static safety contract for the ordered Railway staging cutover."""

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "ci-staging.yml"


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_railway_cli_is_pinned_and_reported() -> None:
    workflow = _workflow_text()

    assert "npm install -g @railway/cli@5.30.4" in workflow
    assert "run: railway --version" in workflow
    assert "npm install -g @railway/cli\n" not in workflow


def test_staging_deployments_do_not_attach_to_flaky_log_streams() -> None:
    workflow = _workflow_text()

    assert (
        "railway up --detach --environment staging --service "
        "${{ secrets.RAILWAY_FRONTEND_SERVICE_ID }}"
    ) in workflow
    assert (
        "railway up --detach --environment staging --service "
        "${{ secrets.RAILWAY_SERVICE_ID }}"
    ) in workflow
    assert "continue-on-error" not in workflow


def test_backend_cutover_remains_ordered_and_release_verified() -> None:
    workflow = _workflow_text()
    ordered_steps = (
        "- name: Deploy Frontend to Railway",
        "- name: Verify V2 City Score Marts Before Backend Cutover",
        "- name: Verify Frontend Release Before Backend Cutover",
        "- name: Stamp Backend Release",
        "- name: Deploy Backend to Railway",
        "- name: Verify Backend Release Before E2E",
        "- name: Reconfirm the deployed staging backend release",
    )

    positions = [workflow.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    assert "backend/app/release_id.txt" in workflow
    assert 'payload.get("release_id")' in workflow
    assert workflow.count('/api/backend-health') >= 2
    assert workflow.count("deadline_seconds=600") >= 2
    assert workflow.count("while (( SECONDS < deadline ))") >= 2
