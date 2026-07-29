from apps.core.time import SystemClock, to_shanghai
from apps.navigation.public import default_site_presentation, public_site_presentation


def site_shell(request):
    presentation = (
        default_site_presentation()
        if getattr(request, "kaj_error_shell", False)
        else public_site_presentation()
    )
    return {
        "site_presentation": presentation,
        "site_year": to_shanghai(SystemClock().now()).year,
    }
