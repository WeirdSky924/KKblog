import unicodedata

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.ids import new_uuid


def normalize_section_name(value: str) -> tuple[str, str]:
    if not isinstance(value, str):
        raise ValidationError("分区名称不合法。")
    display = unicodedata.normalize("NFKC", value).strip()
    if not display or len(display) > 100 or any(ord(char) < 32 for char in display):
        raise ValidationError("分区名称须为 1 至 100 个字符。")
    return display, display.casefold()


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    name = models.CharField(max_length=100)
    normalized_name = models.CharField(max_length=100, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        db_table = "content_section"
        ordering = ("normalized_name", "id")

    def clean(self) -> None:
        self.name, self.normalized_name = normalize_section_name(self.name)

    def save(self, *args, **kwargs) -> None:
        self.clean()
        super().save(*args, **kwargs)
