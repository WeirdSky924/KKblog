from django.db import models

from apps.core.ids import new_uuid


class NavigationTreeState(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "navigation_tree_state"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1),
                name="navigation_tree_singleton_id",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="navigation_tree_version_positive",
            ),
        ]


class NavigationNode(models.Model):
    class NodeType(models.TextChoices):
        INTERNAL_PAGE = "INTERNAL_PAGE", "站内页"
        SECTION = "SECTION", "文章分区"
        EXTERNAL_LINK = "EXTERNAL_LINK", "外链"
        GROUP = "GROUP", "仅分组"

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    label = models.CharField(max_length=80)
    node_type = models.CharField(max_length=20, choices=NodeType.choices)
    target_url = models.CharField(max_length=255, null=True, blank=True)
    target_id = models.CharField(max_length=64, null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        related_name="children",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    position = models.PositiveIntegerField()
    depth = models.PositiveSmallIntegerField()
    hidden = models.BooleanField(default=False)
    default_expanded = models.BooleanField(default=False)
    row_version = models.PositiveBigIntegerField(default=1, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "navigation_node"
        ordering = ("parent_id", "position", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(depth__gte=0, depth__lte=2),
                name="navigation_node_depth_range",
            ),
            models.CheckConstraint(
                condition=models.Q(row_version__gte=1),
                name="navigation_node_version_positive",
            ),
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_id")),
                name="navigation_node_not_own_parent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        node_type="GROUP",
                        target_id__isnull=True,
                        target_url__isnull=True,
                    )
                    | models.Q(
                        node_type="SECTION",
                        target_id__isnull=False,
                        target_url__isnull=True,
                    )
                    | models.Q(
                        node_type__in=("INTERNAL_PAGE", "EXTERNAL_LINK"),
                        target_id__isnull=True,
                        target_url__isnull=False,
                    )
                ),
                name="navigation_node_target_shape",
            ),
            models.UniqueConstraint(
                fields=("position",),
                condition=models.Q(parent__isnull=True),
                name="navigation_root_position_unique",
            ),
            models.UniqueConstraint(
                fields=("parent", "position"),
                condition=models.Q(parent__isnull=False),
                name="navigation_sibling_position_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=("parent", "position", "id"),
                name="navigation_parent_order_idx",
            ),
            models.Index(
                fields=("hidden", "depth", "position"),
                name="navigation_public_tree_idx",
            ),
        ]
