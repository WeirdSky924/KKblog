from collections.abc import Mapping
from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True, slots=True)
class AdminNavigationItem:
    key: str
    label: str
    route_name: str


@dataclass(frozen=True, slots=True)
class AdminNavigationGroup:
    label: str
    items: tuple[AdminNavigationItem, ...]


@dataclass(frozen=True, slots=True)
class ResolvedAdminNavigationItem:
    key: str
    label: str
    route_name: str
    url: str
    review_count: int


@dataclass(frozen=True, slots=True)
class ResolvedAdminNavigationGroup:
    label: str
    items: tuple[ResolvedAdminNavigationItem, ...]


ADMIN_NAVIGATION = (
    AdminNavigationGroup(
        label="账号与访问",
        items=(
            AdminNavigationItem("users", "用户管理", "admin:users"),
            AdminNavigationItem("invites", "邀请码", "admin:invites"),
            AdminNavigationItem("ip-blocks", "IP 封禁", "admin:ip-blocks"),
        ),
    ),
    AdminNavigationGroup(
        label="内容与互动",
        items=(
            AdminNavigationItem("articles", "文章管理", "admin:articles"),
            AdminNavigationItem("comments", "评论管理", "admin:comments"),
            AdminNavigationItem("reports", "举报与申诉", "admin:reports"),
            AdminNavigationItem("tags", "标签审核", "admin:tags"),
            AdminNavigationItem("sections", "文章分区", "admin:sections"),
        ),
    ),
    AdminNavigationGroup(
        label="站点结构",
        items=(
            AdminNavigationItem("navigation", "主页侧边导航", "admin:navigation"),
            AdminNavigationItem("site-settings", "站点设置", "admin:site-settings"),
        ),
    ),
    AdminNavigationGroup(
        label="沟通与数据",
        items=(
            AdminNavigationItem("notifications", "群发通知", "admin:notifications"),
            AdminNavigationItem("exchange", "数据交换", "admin:exchange"),
        ),
    ),
    AdminNavigationGroup(
        label="运行与分析",
        items=(
            AdminNavigationItem("audit", "操作审计", "admin:audit"),
            AdminNavigationItem("errors", "运行错误", "admin:errors"),
            AdminNavigationItem("tasks", "任务与健康", "admin:tasks"),
            AdminNavigationItem("analytics", "访问分析", "admin:analytics"),
        ),
    ),
)


def resolved_admin_navigation(
    *, review_counts: Mapping[str, int] | None = None
) -> tuple[ResolvedAdminNavigationGroup, ...]:
    counts = review_counts or {}
    groups = []
    for group in ADMIN_NAVIGATION:
        items = []
        for item in group.items:
            try:
                url = reverse(item.route_name)
            except NoReverseMatch:
                continue
            items.append(
                ResolvedAdminNavigationItem(
                    key=item.key,
                    label=item.label,
                    route_name=item.route_name,
                    url=url,
                    review_count=max(0, int(counts.get(item.key, 0))),
                )
            )
        if items:
            groups.append(ResolvedAdminNavigationGroup(group.label, tuple(items)))
    return tuple(groups)


def default_admin_route_name() -> str:
    groups = resolved_admin_navigation()
    if not groups:
        raise RuntimeError("Administration has no registered feature route")
    return groups[0].items[0].route_name


__all__ = [
    "ADMIN_NAVIGATION",
    "AdminNavigationGroup",
    "AdminNavigationItem",
    "default_admin_route_name",
    "resolved_admin_navigation",
]
