from django.apps import AppConfig
from django.db.models.signals import pre_delete


class CommentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.comments"

    def ready(self) -> None:
        from apps.content.public import register_article_comment_purge

        from .services.purge import purge_article_comments
        from .signals import anonymize_deleted_account_comments

        account_model = self.apps.get_model("accounts", "Account")
        pre_delete.connect(
            anonymize_deleted_account_comments,
            sender=account_model,
            dispatch_uid="comments.anonymize_account",
        )
        register_article_comment_purge(purge_article_comments, replace=True)
