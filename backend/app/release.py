"""Build identity exposed by the backend health endpoint.

Staging CI overwrites ``release_id.txt`` before uploading the backend source.
Keeping the identity in the deployed image makes the rollout gate independent
of Railway-specific runtime metadata.
"""

from pathlib import Path


DEFAULT_RELEASE_ID = "local-development"
RELEASE_ID_PATH = Path(__file__).with_name("release_id.txt")


def read_release_id() -> str:
    """Return the image's stamped release identity or a deterministic local ID."""
    try:
        release_id = RELEASE_ID_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_RELEASE_ID

    return release_id or DEFAULT_RELEASE_ID


RELEASE_ID = read_release_id()
