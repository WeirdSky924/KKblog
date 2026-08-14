from django.db import migrations, models

from apps.media.migration_cleanup import release_legacy_target_assets


def retire_friend_link_logos(apps, schema_editor) -> None:
    release_legacy_target_assets(
        apps=apps,
        schema_editor=schema_editor,
        target_type="friend_link",
    )
    apps.get_model("navigation", "FriendLink").objects.using(
        schema_editor.connection.alias
    ).update(logo_asset_id="")


class Migration(migrations.Migration):
    dependencies = [
        ("media", "0006_remove_mediaasset_media_asset_size_range_and_more"),
        ("navigation", "0006_site_hero_media"),
    ]

    operations = [
        migrations.RunPython(
            retire_friend_link_logos,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="friendlink",
            name="logo_asset_id",
            field=models.CharField(blank=True, default="", max_length=26),
        ),
    ]
