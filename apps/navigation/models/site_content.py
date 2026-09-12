from django.db import models

from apps.core.ids import new_uuid

from ..site_contracts import (
    DEFAULT_ARTICLE_EXPLANATION_DAILY_LIMIT,
    DEFAULT_ARTICLE_EXPLANATION_HISTORY_LIMIT,
    DEFAULT_ARTICLE_EXPLANATION_MINUTE_LIMIT,
    DEFAULT_ARTICLE_EXPLANATION_SELECTION_LIMIT,
    MAX_ARTICLE_EXPLANATION_DAILY_LIMIT,
    MAX_ARTICLE_EXPLANATION_HISTORY_LIMIT,
    MAX_ARTICLE_EXPLANATION_MINUTE_LIMIT,
    MAX_ARTICLE_EXPLANATION_SELECTION_LIMIT,
    MIN_ARTICLE_EXPLANATION_DAILY_LIMIT,
    MIN_ARTICLE_EXPLANATION_HISTORY_LIMIT,
    MIN_ARTICLE_EXPLANATION_MINUTE_LIMIT,
    MIN_ARTICLE_EXPLANATION_SELECTION_LIMIT,
    SITE_MAX_ARTICLE_BODY_BYTES,
    SITE_MIN_ARTICLE_BODY_BYTES,
    STATIC_PAGE_FORMAT_CHOICES,
    STATIC_PAGE_TYPE_CHOICES,
)


class SiteConfiguration(models.Model):
    MIN_ARTICLE_BODY_BYTES = SITE_MIN_ARTICLE_BODY_BYTES
    MAX_ARTICLE_BODY_BYTES = SITE_MAX_ARTICLE_BODY_BYTES

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField(max_length=100, default="Kaj的小房间")
    site_description = models.CharField(max_length=200, blank=True, default="")
    copyright_text = models.CharField(max_length=200, blank=True, default="")
    registration_enabled = models.BooleanField(default=False)
    article_body_max_bytes = models.PositiveIntegerField(
        default=SITE_MAX_ARTICLE_BODY_BYTES
    )
    logo_asset_id = models.CharField(max_length=26, null=True, blank=True)
    hero_asset_id = models.CharField(max_length=26, null=True, blank=True)
    verification_email_template = models.TextField(blank=True, default="")
    backup_destination = models.CharField(max_length=16, default="local")
    article_explanation_daily_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_ARTICLE_EXPLANATION_DAILY_LIMIT
    )
    article_explanation_minute_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_ARTICLE_EXPLANATION_MINUTE_LIMIT
    )
    article_explanation_selection_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_ARTICLE_EXPLANATION_SELECTION_LIMIT
    )
    article_explanation_history_limit = models.PositiveSmallIntegerField(
        default=DEFAULT_ARTICLE_EXPLANATION_HISTORY_LIMIT
    )
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "site_configuration"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1),
                name="site_configuration_singleton_id",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    article_body_max_bytes__gte=SITE_MIN_ARTICLE_BODY_BYTES,
                    article_body_max_bytes__lte=SITE_MAX_ARTICLE_BODY_BYTES,
                ),
                name="site_configuration_body_limit_range",
            ),
            models.CheckConstraint(
                condition=models.Q(backup_destination="local"),
                name="site_configuration_local_backup_only",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="site_configuration_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    article_explanation_daily_limit__gte=MIN_ARTICLE_EXPLANATION_DAILY_LIMIT,
                    article_explanation_daily_limit__lte=MAX_ARTICLE_EXPLANATION_DAILY_LIMIT,
                ),
                name="site_configuration_explain_daily_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    article_explanation_minute_limit__gte=MIN_ARTICLE_EXPLANATION_MINUTE_LIMIT,
                    article_explanation_minute_limit__lte=MAX_ARTICLE_EXPLANATION_MINUTE_LIMIT,
                ),
                name="site_configuration_explain_minute_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    article_explanation_selection_limit__gte=MIN_ARTICLE_EXPLANATION_SELECTION_LIMIT,
                    article_explanation_selection_limit__lte=MAX_ARTICLE_EXPLANATION_SELECTION_LIMIT,
                ),
                name="site_configuration_explain_selection_range",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    article_explanation_history_limit__gte=MIN_ARTICLE_EXPLANATION_HISTORY_LIMIT,
                    article_explanation_history_limit__lte=MAX_ARTICLE_EXPLANATION_HISTORY_LIMIT,
                ),
                name="site_configuration_explain_history_range",
            ),
        ]


class StaticPage(models.Model):
    class PageType(models.TextChoices):
        ABOUT = STATIC_PAGE_TYPE_CHOICES[0]
        PRIVACY = STATIC_PAGE_TYPE_CHOICES[1]
        TERMS = STATIC_PAGE_TYPE_CHOICES[2]

    class ContentFormat(models.TextChoices):
        MARKDOWN = STATIC_PAGE_FORMAT_CHOICES[0]
        RICH_TEXT = STATIC_PAGE_FORMAT_CHOICES[1]

    page_type = models.CharField(
        primary_key=True,
        max_length=16,
        choices=PageType.choices,
    )
    content_format = models.CharField(
        max_length=16,
        choices=ContentFormat.choices,
        default=ContentFormat.MARKDOWN,
    )
    source = models.TextField(blank=True, default="")
    published = models.BooleanField(default=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "static_page"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="static_page_version_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(published=False) | ~models.Q(source=""),
                name="static_page_published_has_source",
            ),
        ]


class FriendLink(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    name = models.CharField(max_length=80)
    url = models.CharField(max_length=255)
    description = models.CharField(max_length=300)
    # Deprecated compatibility column. New friend links never store media IDs.
    logo_asset_id = models.CharField(max_length=26, blank=True, default="")
    position = models.PositiveIntegerField()
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "friend_link"
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("position",),
                name="friend_link_position_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="friend_link_version_positive",
            ),
        ]


class TrustedEmbedSource(models.Model):
    source_key = models.CharField(primary_key=True, max_length=32)
    display_name = models.CharField(max_length=80)
    host_pattern = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "trusted_embed_source"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="trusted_embed_source_version_positive",
            ),
        ]
