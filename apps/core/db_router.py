"""
Read-replica database router for EduOS.

Sends read-only queries to the replica when explicitly opted in via
`.using('replica')` in selectors. All writes always go to default.
"""


class ReadReplicaRouter:
    """
    Routes read queries to the replica database when explicitly requested.
    All writes always go to the default (primary) database.
    """

    def db_for_read(self, model, **hints):
        """
        Default reads go to primary. Selectors opt into replica
        via queryset.using('replica').
        """
        return None  # Let Django decide (default)

    def db_for_write(self, model, **hints):
        """All writes go to the primary database."""
        return "default"

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations between objects in default and replica."""
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Only run migrations on the default database."""
        return db == "default"
