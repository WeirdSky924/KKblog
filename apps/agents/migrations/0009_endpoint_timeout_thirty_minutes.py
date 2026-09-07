from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0008_agentendpoint_reasoning_effort_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="agentendpoint",
            name="agent_endpoint_timeout_range",
        ),
        migrations.AddConstraint(
            model_name="agentendpoint",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("request_timeout_seconds__gte", 10),
                    ("request_timeout_seconds__lte", 1800),
                ),
                name="agent_endpoint_timeout_range",
            ),
        ),
    ]
