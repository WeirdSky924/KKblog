from apps.comments.models import Comment


def anonymize_deleted_account_comments(sender, instance, **kwargs) -> None:
    Comment.objects.filter(author_id=instance.id).update(
        author_id=None,
        author_kind=Comment.AuthorKind.DELETED_ACCOUNT,
    )
