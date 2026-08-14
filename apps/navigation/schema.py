from django.db import connection


def site_hero_column_available() -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = 'site_configuration' "
            "AND column_name = 'hero_asset_id'"
            ")"
        )
        row = cursor.fetchone()
    return bool(row and row[0])


__all__ = ["site_hero_column_available"]
