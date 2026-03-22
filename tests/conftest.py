# tests/conftest.py
import os
import pytest
import sqlite3
from src.db import init_db, get_connection

@pytest.fixture
def db_conn():
    """In-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()
