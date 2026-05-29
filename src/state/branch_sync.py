import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
BRANCH = "state"
WORK_BRANCH = "state-tmp"


def build_orphan_commit_args(db_path: Path, message: str) -> dict:
    return {
        "checkout": ["git", "checkout", "--orphan", WORK_BRANCH],
        "add":     ["git", "add", "-f", db_path.as_posix()],
        "commit_msg": message,
        "push_refspec": f"{WORK_BRANCH}:{BRANCH}",
    }


def _run(cmd: list[str], check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    logger.debug("git: %s", " ".join(cmd))
    return subprocess.run(cmd, check=check,
                          capture_output=capture, text=True)


def restore(db_path: Path) -> bool:
    """Fetch state branch and check out the DB file. Returns True if restored."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["git", "fetch", "origin", BRANCH], check=False, capture=True)
    if r.returncode != 0:
        logger.info("state branch not found — bootstrapping empty DB")
        return False
    _run(["git", "checkout", f"origin/{BRANCH}", "--", db_path.as_posix()])
    logger.info("state branch restored: %s", db_path)
    return True


def commit_and_push(db_path: Path, message: str,
                    artifact_dir: Path | None = None) -> None:
    """Force-push DB as a single-commit orphan branch.

    On push failure: retry once with `git pull --rebase`; on second fail,
    copy DB to artifact_dir (caller uploads it via actions/upload-artifact).
    """
    args = build_orphan_commit_args(db_path, message)
    _run(args["checkout"])
    _run(args["add"])
    _run(["git", "commit", "-m", args["commit_msg"]])
    push = _run(["git", "push", "--force", "origin", args["push_refspec"]],
                check=False, capture=True)
    if push.returncode != 0:
        logger.warning("push failed (%s), retrying after pull --rebase",
                       push.stderr.strip())
        _run(["git", "pull", "--rebase", "origin", BRANCH], check=False)
        push2 = _run(["git", "push", "--force", "origin", args["push_refspec"]],
                     check=False, capture=True)
        if push2.returncode != 0:
            if artifact_dir is not None:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_path, artifact_dir / db_path.name)
                logger.error("push failed twice — DB saved to %s", artifact_dir)
            raise RuntimeError(f"state push failed: {push2.stderr.strip()}")
    _run(["git", "checkout", "-"])
