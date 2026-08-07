from apps.core.time import SystemClock, to_shanghai
from apps.navigation.public import (
    default_site_presentation,
    public_site_presentation,
    visible_friend_links,
)


def site_shell(request):
    if getattr(request, "kaj_error_shell", False):
        presentation = default_site_presentation()
        footer_friend_links = ()
    else:
        presentation = public_site_presentation()
        footer_friend_links = visible_friend_links()
    return {
        "site_presentation": presentation,
        "site_year": to_shanghai(SystemClock().now()).year,
        "footer_friend_links": footer_friend_links,
    }
