from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0009_endpoint_timeout_thirty_minutes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agentprofile",
            name="purpose",
            field=models.CharField(
                choices=[
                    ("KNOWLEDGE_REVIEW", "Knowledge review"),
                    ("QUESTION_GENERATION", "Question generation"),
                    ("ARTICLE_EXPLANATION", "Article explanation"),
                ],
                max_length=24,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="agentprofile",
            name="agent_profile_purpose_valid",
        ),
        migrations.AddConstraint(
            model_name="agentprofile",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    purpose__in=(
                        "KNOWLEDGE_REVIEW",
                        "QUESTION_GENERATION",
                        "ARTICLE_EXPLANATION",
                    )
                ),
                name="agent_profile_purpose_valid",
            ),
        ),
    ]
