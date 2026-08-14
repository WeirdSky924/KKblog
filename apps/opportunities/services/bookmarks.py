from apps.accounts.public import is_active_account

from ..models import Opportunity, OpportunityBookmark
from ..policies import publicly_available_opportunity
from .common import OpportunityCommandError, uuid_value


def set_opportunity_bookmark(*, account_id, opportunity_id, selected: bool) -> bool:
    account = uuid_value(
        account_id,
        code="opportunities.login_required.v1",
        message="请登录后使用岗位收藏。",
    )
    if not is_active_account(account):
        raise OpportunityCommandError(
            "opportunities.login_required.v1", "请登录后使用岗位收藏。"
        )
    identity = uuid_value(
        opportunity_id,
        code="opportunities.opportunity_not_found.v1",
        message="岗位不存在。",
    )
    if not isinstance(selected, bool):
        raise OpportunityCommandError(
            "opportunities.bookmark_state_invalid.v1", "收藏状态不合法。"
        )
    opportunity_exists = Opportunity.objects.filter(pk=identity).exists()
    if not opportunity_exists:
        raise OpportunityCommandError(
            "opportunities.opportunity_not_found.v1", "岗位不存在。"
        )
    if selected:
        if not Opportunity.objects.filter(
            publicly_available_opportunity(),
            pk=identity,
        ).exists():
            raise OpportunityCommandError(
                "opportunities.opportunity_not_public.v1",
                "该岗位当前不可收藏。",
            )
        OpportunityBookmark.objects.get_or_create(
            account_id=account,
            opportunity_id=identity,
        )
        return True
    OpportunityBookmark.objects.filter(
        account_id=account,
        opportunity_id=identity,
    ).delete()
    return False


__all__ = ["set_opportunity_bookmark"]
