from django.http import HttpRequest

HTMX_VARIANT_HEADERS = ("HX-Request", "HX-Boosted")


def is_htmx_fragment_request(request: HttpRequest) -> bool:
    """Return true only when the caller expects a component-sized response."""
    return (
        request.headers.get("HX-Request", "").casefold() == "true"
        and request.headers.get("HX-Boosted", "").casefold() != "true"
    )
