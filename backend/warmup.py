"""Warm public content and signing setup before a Gunicorn worker serves users."""
import time


def warm_public_content(app):
    started=time.perf_counter()
    with app.app_context():
        from .models import db
        from .storage import client,enabled
        # Creating the signer performs no R2 GET/PUT and exposes no asset.
        if enabled() and app.config.get('IMAGE_DELIVERY')=='signed':
            client()
        try:
            from .api import home
            with app.test_request_context('/api/home'):
                home()
        finally:
            db.session.remove()
    return round((time.perf_counter()-started)*1000)
