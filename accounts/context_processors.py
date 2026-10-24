from django.conf import settings
from django.urls import NoReverseMatch, reverse


def nav_links(request):
    """Builds the nav bar from settings.MODELMESH_NAV so each app can add its own link."""
    links = []
    for label, url_name in settings.MODELMESH_NAV:
        try:
            url = reverse(url_name)
        except NoReverseMatch:
            continue
        links.append({"label": label, "url": url, "active": request.path.startswith(url)})
    return {"nav_links": links}
