"""Shared fixtures for e2e tests."""

import pytest

# Import fixtures from test_e2e_real to make them available across all e2e test modules
pytest_plugins = ["tests.e2e.test_e2e_real"]