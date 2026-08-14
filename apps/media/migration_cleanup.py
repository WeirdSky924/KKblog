def release_legacy_target_assets(*, apps, schema_editor, target_type: str) -> None:
    """Detach retired bindings without touching files inside a schema transaction."""
    media_asset = apps.get_model("media", "MediaAsset")
    media_binding = apps.get_model("media", "MediaBinding")
    database = schema_editor.connection.alias
    bindings = media_binding.objects.using(database).filter(target_type=target_type)
    asset_ids = tuple(
        bindings.order_by("asset_id").values_list("asset_id", flat=True).distinct()
    )
    if not asset_ids:
        return
    bindings.delete()
    retained_ids = (
        media_binding.objects.using(database)
        .filter(asset_id__in=asset_ids)
        .values_list("asset_id", flat=True)
    )
    media_asset.objects.using(database).filter(
        id__in=asset_ids,
        state__in=("STAGED", "ACTIVE"),
    ).exclude(id__in=retained_ids).update(state="DELETE_PENDING")


__all__ = ["release_legacy_target_assets"]
