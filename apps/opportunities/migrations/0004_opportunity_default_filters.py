import django.db.models.deletion
from django.db import migrations, models


def copy_existing_defaults(apps, schema_editor):
    settings_model = apps.get_model("opportunities", "OpportunitySettings")
    selection_model = apps.get_model(
        "opportunities", "OpportunityDefaultFilterSelection"
    )
    selections = []
    for settings in settings_model.objects.all().iterator():
        selections.extend(
            (
                selection_model(
                    settings_id=settings.pk,
                    kind="STATUS",
                    value="CONFIRMED",
                ),
                selection_model(
                    settings_id=settings.pk,
                    kind="STATUS",
                    value="PENDING",
                ),
            )
        )
        if settings.default_city_id:
            selections.append(
                selection_model(
                    settings_id=settings.pk,
                    kind="CITY",
                    option_id=settings.default_city_id,
                )
            )
        if settings.default_cohort_id:
            selections.append(
                selection_model(
                    settings_id=settings.pk,
                    kind="COHORT",
                    option_id=settings.default_cohort_id,
                )
            )
    selection_model.objects.bulk_create(selections)


class Migration(migrations.Migration):
    dependencies = [
        ("opportunities", "0003_opportunity_composite_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpportunityDefaultFilterSelection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("CITY", "城市"),
                            ("STATUS", "核实状态"),
                            ("COMPANY", "企业"),
                            ("RECRUITMENT_TYPE", "招聘类型"),
                            ("CATEGORY", "岗位类别"),
                            ("COHORT", "届别"),
                        ],
                        max_length=20,
                    ),
                ),
                ("value", models.CharField(blank=True, max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "option",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="opportunities.opportunityfilteroption",
                    ),
                ),
                (
                    "settings",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="default_filter_selections",
                        to="opportunities.opportunitysettings",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to="opportunities.opportunitysource",
                    ),
                ),
            ],
            options={
                "db_table": "opportunity_default_filter_selection",
                "ordering": ("kind", "id"),
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            (
                                "kind__in",
                                (
                                    "CITY",
                                    "STATUS",
                                    "COMPANY",
                                    "RECRUITMENT_TYPE",
                                    "CATEGORY",
                                    "COHORT",
                                ),
                            )
                        ),
                        name="opp_default_filter_kind_valid",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("kind__in", ("CITY", "CATEGORY", "COHORT")),
                                ("option__isnull", False),
                                ("source__isnull", True),
                                ("value", ""),
                            ),
                            models.Q(
                                ("kind", "COMPANY"),
                                ("option__isnull", True),
                                ("source__isnull", False),
                                ("value", ""),
                            ),
                            models.Q(
                                ("kind__in", ("STATUS", "RECRUITMENT_TYPE")),
                                ("option__isnull", True),
                                ("source__isnull", True),
                                models.Q(("value", ""), _negated=True),
                            ),
                            _connector="OR",
                        ),
                        name="opp_default_filter_shape",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("option__isnull", False)),
                        fields=("settings", "kind", "option"),
                        name="opp_default_filter_option_unique",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("source__isnull", False)),
                        fields=("settings", "kind", "source"),
                        name="opp_default_filter_source_unique",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("value", ""), _negated=True),
                        fields=("settings", "kind", "value"),
                        name="opp_default_filter_value_unique",
                    ),
                ],
            },
        ),
        migrations.RunPython(copy_existing_defaults, migrations.RunPython.noop),
    ]
