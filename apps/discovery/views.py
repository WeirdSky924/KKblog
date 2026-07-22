from django.shortcuts import render


def home(request):
    return render(
        request,
        "discovery/home.html",
        {"signed_in": getattr(request, "account_id", None) is not None},
    )
