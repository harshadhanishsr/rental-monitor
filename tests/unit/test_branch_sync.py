from pathlib import Path
from src.state.branch_sync import build_orphan_commit_args

def test_orphan_commit_args_includes_db_path():
    args = build_orphan_commit_args(db_path=Path("data/rental_monitor.db"),
                                    message="state: test")
    assert "--orphan" in args["checkout"]
    assert "state-tmp" in args["checkout"]
    assert "data/rental_monitor.db" in args["add"]
    assert args["commit_msg"] == "state: test"
    assert args["push_refspec"] == "state-tmp:state"
