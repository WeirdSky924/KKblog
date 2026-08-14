from django.urls import reverse

from apps.accounts.public import (
    DEFAULT_VERIFICATION_EMAIL_TEMPLATE,
    VerificationEmailConfiguration,
)
from apps.navigation.public import SitePresentation
from apps.navigation.queries import (
    public_navigation_tree,
    public_site_configuration,
    static_page_is_published,
)


def database_site_presentation() -> SitePresentation:
    configuration = public_site_configuration()
    about_url = reverse("public:about")

    def include_about(items):
        result = []
        for item in items:
            children = include_about(item.children)
            if item.url == about_url and not static_page_is_published("ABOUT"):
                continue
            if item.url is None and not children:
                continue
            result.append(
                item.__class__(
                    label=item.label,
                    url=item.url,
                    children=tuple(children),
                    key=item.key,
                    section_id=item.section_id,
                    default_expanded=item.default_expanded and bool(children),
                )
            )
        return result

    navigation = tuple(include_about(public_navigation_tree()))
    privacy_url = (
        reverse("public:privacy") if static_page_is_published("PRIVACY") else None
    )
    terms_url = reverse("public:terms") if static_page_is_published("TERMS") else None
    return SitePresentation(
        site_name=configuration.site_name,
        site_description=configuration.site_description or None,
        logo_url=configuration.logo_url,
        hero_url=configuration.hero_url,
        hero_is_video=configuration.hero_is_video,
        navigation=navigation,
        copyright_text=configuration.copyright_text or None,
        privacy_url=privacy_url,
        terms_url=terms_url,
    )


def verification_email_configuration() -> VerificationEmailConfiguration:
    configuration = public_site_configuration()
    return VerificationEmailConfiguration(
        site_name=configuration.site_name,
        template_source=(
            configuration.verification_email_template
            or DEFAULT_VERIFICATION_EMAIL_TEMPLATE
        ),
    )


__all__ = ["database_site_presentation", "verification_email_configuration"]
