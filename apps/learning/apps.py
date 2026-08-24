from django.apps import AppConfig


class LearningConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.learning"

    def ready(self) -> None:
        from apps.accounts.public import configure_account_deletion_cleanup

        from .audit_schemas import register_learning_audit_schemas
        from .generation_schema import register_question_generation_schema
        from .media_access import register_media_access
        from .review_schema import register_learning_review_schema

        def purge_learning_account(account_id):
            from .services.cleanup import purge_account_learning_data

            return purge_account_learning_data(account_id=account_id)

        register_learning_audit_schemas()
        register_question_generation_schema()
        register_learning_review_schema()
        register_media_access()
        configure_account_deletion_cleanup(purge_learning_account)
