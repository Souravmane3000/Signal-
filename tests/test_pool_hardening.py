"""Pool hardening config for Supabase / PgBouncer stale-connection safety."""

from agent.graph import (
    _check_pool_connection,
    _postgres_saver,
    _postgres_store,
    pool,
)


def test_pool_idle_and_lifetime_below_cloud_defaults():
    """Defaults (max_idle=600, max_lifetime=3600) are too long for Supabase."""
    assert pool.min_size == 0
    assert pool.max_size == 5
    assert pool.max_idle == 180.0
    assert pool.max_lifetime == 1800.0
    assert pool.reconnect_timeout == 60.0


def test_pool_checkout_uses_discarding_health_check():
    assert pool._check is _check_pool_connection


def test_pool_kwargs_disable_prepared_stmts_and_enable_keepalives():
    kwargs = pool.kwargs
    assert kwargs["prepare_threshold"] == 0
    assert kwargs["autocommit"] is True
    assert kwargs["keepalives"] == 1
    assert kwargs["keepalives_idle"] == 30
    assert kwargs["connect_timeout"] == 10


def test_saver_and_store_disable_pipeline_mode():
    assert _postgres_saver.supports_pipeline is False
    assert _postgres_store.supports_pipeline is False
