"""
OIDC Logout URL generator for Authentik

Generates the proper logout URL for Authentik end-session endpoint.
"""

from django.conf import settings


def get_logout_url(request):
    """
    Generate the Authentik logout URL with proper redirect.
    
    This is called by mozilla-django-oidc to build the logout URL.
    """
    logout_endpoint = getattr(
        settings, 
        'OIDC_OP_LOGOUT_ENDPOINT',
        f"{settings.AUTHENTIK_URL}/application/o/smart-hotel/end-session/"
    )
    
    # Get the ID token from session for logout
    id_token = request.session.get('oidc_id_token')
    
    # Build the redirect URI (where to go after logout)
    redirect_uri = request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL)
    
    # Build logout URL with parameters
    if id_token:
        return f"{logout_endpoint}?id_token_hint={id_token}&post_logout_redirect_uri={redirect_uri}"
    else:
        return f"{logout_endpoint}?post_logout_redirect_uri={redirect_uri}"
