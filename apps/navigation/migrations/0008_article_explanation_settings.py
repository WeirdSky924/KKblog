from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("navigation", "0007_retire_friend_link_logos"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_explanation_daily_limit",
            field=models.PositiveSmallIntegerField(default=50),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_explanation_minute_limit",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_explanation_selection_limit",
            field=models.PositiveSmallIntegerField(default=1000),
        ),
        migrations.AddField(
            model_name="siteconfiguration",
            name="article_explanation_history_limit",
            field=models.PositiveSmallIntegerField(default=30),
        ),
        migrations.AddConstraint(
            model_name="siteconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    article_explanation_daily_limit__gte=1,
                    article_explanation_daily_limit__lte=1000,
                ),
                name="site_configuration_explain_daily_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="siteconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    article_explanation_minute_limit__gte=1,
                    article_explanation_minute_limit__lte=60,
                ),
                name="site_configuration_explain_minute_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="siteconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    article_explanation_selection_limit__gte=1,
                    article_explanation_selection_limit__lte=10000,
                ),
                name="site_configuration_explain_selection_range",
            ),
        ),
        migrations.AddConstraint(
            model_name="siteconfiguration",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    article_explanation_history_limit__gte=1,
                    article_explanation_history_limit__lte=100,
                ),
                name="site_configuration_explain_history_range",
            ),
        ),
    ]
