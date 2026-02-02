"""Pytest configuration for cacheql tests."""

import pytest


@pytest.fixture(autouse=True)
def reset_decorator_config():
    """Reset decorator configuration before each test."""
    import cacheql.decorators

    # Store original values
    original_service = cacheql.decorators._cache_service
    original_builder = cacheql.decorators._key_builder

    yield

    # Restore original values after test
    cacheql.decorators._cache_service = original_service
    cacheql.decorators._key_builder = original_builder
