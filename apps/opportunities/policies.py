from django.db.models import Q

from .models import Opportunity


def publicly_available_opportunity() -> Q:
    return Q(
        source__enabled=True,
        source__publicly_visible=True,
        publication_state=Opportunity.PublicationState.PUBLISHED,
        list_missing=False,
        verification_status__in=(
            Opportunity.VerificationStatus.CONFIRMED,
            Opportunity.VerificationStatus.PENDING,
        ),
    )


__all__ = ["publicly_available_opportunity"]
