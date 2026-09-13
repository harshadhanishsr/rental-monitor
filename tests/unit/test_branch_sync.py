from pathlib import Path
from src.state.branch_sync import build_orphan_commit_args, is_nothing_to_commit

def test_orphan_commit_args_includes_db_path():
    args = build_orphan_commit_args(db_path=Path("data/rental_monitor.db"),
                                    message="state: test")
    assert "--orphan" in args["checkout"]
    assert "state-tmp" in args["checkout"]
    assert "data/rental_monitor.db" in args["add"]
    assert args["commit_msg"] == "state: test"
    assert args["push_refspec"] == "state-tmp:state"


def test_is_nothing_to_commit_detects_message():
    # Typical git outputs that mean "nothing to commit"
    assert is_nothing_to_commit("nothing to commit, working tree clean")
    assert is_nothing_to_commit("On branch state-tmp\nnothing to commit, working tree clean\n")
    assert is_nothing_to_commit("no changes added to commit (use \"git add\" and/or \"git commit -a\")")
    assert is_nothing_to_commit("nothing to commit")
    # Should NOT match unrelated stderr
    assert not is_nothing_to_commit("error: failed to push some refs")
    assert not is_nothing_to_commit("fatal: repository not found")
    assert not is_nothing_to_commit("")


def test_build_orphan_commit_args_uses_posix_path_on_windows_input():
    # Simulate a path constructed with backslashes (Windows-style)
    p = Path(r"data\rental_monitor.db")
    args = build_orphan_commit_args(db_path=p, message="state: windows")
    # The add list must contain the forward-slash form
    assert "data/rental_monitor.db" in args["add"]
