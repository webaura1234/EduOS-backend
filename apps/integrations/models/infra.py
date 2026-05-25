"""
Integrations — reliability infrastructure.

  - OutboxEvent    → transactional outbox pattern — events to be published after DB commit
  - IdempotencyKey → per-request idempotency store to prevent duplicate processing
  - RateLimitTier  → per-tenant or per-endpoint rate limit configuration
"""

# TODO: Implement models in this file.
# Suggested models: OutboxEvent, IdempotencyKey, RateLimitTier
