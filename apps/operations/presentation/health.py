from django.http import HttpRequest, JsonResponse

from apps.operations.services.health import ReadinessUnavailable, check_readiness


def _response(status: str, status_code: int = 200) -> JsonResponse:
    response = JsonResponse({"status": status}, status=status_code)
    response.headers["Cache-Control"] = "no-store"
    return response


def live(request: HttpRequest) -> JsonResponse:
    del request
    return _response("live")


def ready(request: HttpRequest) -> JsonResponse:
    del request
    try:
        check_readiness()
    except ReadinessUnavailable:
        return _response("unavailable", status_code=503)
    return _response("ready")
