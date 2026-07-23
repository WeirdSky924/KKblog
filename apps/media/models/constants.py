from django.db import models


class MediaPurpose(models.TextChoices):
    AVATAR = "AVATAR", "头像"
    COVER = "COVER", "文章封面"
    BODY = "BODY", "正文图片"
    COMMENT = "COMMENT", "评论图片"
    EVIDENCE = "EVIDENCE", "审核证据"
    LOGO = "LOGO", "站点标志"
    FRIEND_LOGO = "FRIEND_LOGO", "友情链接标志"
    IMPORT = "IMPORT", "导入源图片"


class DetectedFormat(models.TextChoices):
    PNG = "image/png", "PNG"
    JPEG = "image/jpeg", "JPEG"
    GIF = "image/gif", "GIF"
    WEBP = "image/webp", "WebP"
    ICO = "image/x-icon", "ICO"


class MediaState(models.TextChoices):
    STAGED = "STAGED", "暂存"
    ACTIVE = "ACTIVE", "可用"
    DELETE_PENDING = "DELETE_PENDING", "待删除"
    DELETED = "DELETED", "已删除"


class MediaTargetType(models.TextChoices):
    ACCOUNT_PROFILE = "account_profile", "账户资料"
    ARTICLE_REVISION = "article_revision", "文章修订"
    COMMENT = "comment", "评论"
    REPORT = "report", "举报"
    REPORT_APPEAL = "report_appeal", "举报申诉"
    ARTICLE_APPEAL = "article_appeal", "文章申诉"
    SITE_BRAND = "site_brand", "站点品牌"
    FRIEND_LINK = "friend_link", "友情链接"
    IMPORT_JOB = "import_job", "导入任务"
