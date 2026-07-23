from apps.core.time import SystemClock, to_shanghai
from apps.navigation.public import public_site_presentation


def site_shell(request):
    del request
    return {
        "site_presentation": public_site_presentation(),
        "site_year": to_shanghai(SystemClock().now()).year,
    }
