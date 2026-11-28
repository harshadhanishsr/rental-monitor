"""Legacy v1 modules — preserved during the v2 rollout window.

These files are no longer imported by ``src.core.engine`` or its dependants.
They live here so the v1 CLI (and the cutover seed script's reference to
``seen_listings``) still works while the migration settles. Scheduled for
removal in Task 6.1.
"""
