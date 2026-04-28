from app.core.config import settings


def table_name(suffix: str) -> str:
    """
    Build a table name using the global Camme prefix convention.
    Example: table_name("users") -> "camme_users"
    """
    normalized = suffix.strip().lower()
    if not normalized:
        raise ValueError("Table name suffix cannot be empty")
    return f"{settings.db_table_prefix}{normalized}"
