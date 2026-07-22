from django.core.exceptions import ValidationError
from django.db import models


class RoleAssignment(models.Model):
    class Role(models.TextChoices):
        AUTHOR = "AUTHOR", "作者"
        ADMINISTRATOR = "ADMINISTRATOR", "管理员"

    account = models.ForeignKey(
        "accounts.Account", related_name="roles", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    granted_by = models.ForeignKey(
        "accounts.Account",
        related_name="roles_granted",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "account_role_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["account", "role"], name="account_role_unique"
            ),
            models.UniqueConstraint(
                fields=["role"],
                condition=models.Q(role="ADMINISTRATOR"),
                name="one_administrator_role",
            ),
        ]

    def delete(self, *args, **kwargs):
        if (
            self.role == self.Role.AUTHOR
            and self.account.roles.filter(role=self.Role.ADMINISTRATOR).exists()
        ):
            raise ValidationError("管理员必须同时保留作者角色")
        if self.role == self.Role.ADMINISTRATOR:
            raise ValidationError("唯一管理员角色不能撤销")
        return super().delete(*args, **kwargs)
