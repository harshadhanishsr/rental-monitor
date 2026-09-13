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


def is_nothing_to_commit(output: str) -> bool:
    """Return True if git output indicates there is nothing to commit."""
    lowered = output.lower()
    return "nothing to commit" in lowered or "no changes added to commit" in lowered


def _run(cmd: list[str], check: bool = True,
         capture: bool = False) -> subprocess.CompletedProcess:
    logger.debug("git: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(cmd[1:])} failed: {result.stderr.strip()}"
        )
    return result


def restore(db_path: Path) -> bool:
    """Fetch state branch and check out the DB file. Returns True if restored."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # First, check whether the remote branch actually exists.
    ls = _run(["git", "ls-remote", "--heads", "origin", BRANCH],
              check=False, capture=True)
    if ls.returncode != 0:
        raise RuntimeError(f"failed to query state branch: {ls.stderr.strip()}")
    if not ls.stdout.strip():
        logger.info("state branch not found — bootstrapping empty DB")
        return False

    # Branch exists — fetch it (failure is now unexpected, so raise).
    _run(["git", "fetch", "origin", BRANCH])

    _run(["git", "checkout", f"origin/{BRANCH}", "--", db_path.as_posix()])
    if not db_path.exists():
        raise RuntimeError("state branch present but db file missing")
    logger.info("state branch restored: %s", db_path)
    return True


def commit_and_push(db_path: Path, message: str,
                    artifact_dir: Path | None = None) -> None:
    """Force-push DB as a single-commit orphan branch.

    On push failure: retry once with `git pull --rebase`; on second fail,
    copy DB to artifact_dir (caller uploads it via actions/upload-artifact).
    """
    # Capture starting ref so we can restore it reliably in finally.
    ref_result = _run(["git", "symbolic-ref", "--short", "HEAD"],
                      check=False, capture=True)
    if ref_result.returncode == 0:
        origin_ref = ref_result.stdout.strip()
    else:
        # Detached HEAD — fall back to commit hash.
        origin_ref = _run(["git", "rev-parse", "HEAD"],
                          check=False, capture=True).stdout.strip()

    args = build_orphan_commit_args(db_path, message)

    try:
        # Idempotent: delete state-tmp if it already exists.
        _run(["git", "branch", "-D", WORK_BRANCH], check=False, capture=True)

        _run(args["checkout"])
        _run(args["add"])

        # Fix 4: handle "nothing to commit"
        commit_result = _run(["git", "commit", "-m", args["commit_msg"]],
                             check=False, capture=True)
        if commit_result.returncode != 0:
            combined = commit_result.stdout + commit_result.stderr
            if is_nothing_to_commit(combined):
                logger.info("state unchanged — skipping push")
                return
            raise RuntimeError(
                f"git commit failed: {commit_result.stderr.strip()}"
            )

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
    finally:
        # Always restore the original branch, even if an exception was raised.
        _run(["git", "checkout", origin_ref], check=False, capture=True)
