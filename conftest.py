"""
Root conftest for pytest.

Shared fixtures available to all test modules.
"""

import pytest


@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """Allow all tests to access the database by default."""
    pass
