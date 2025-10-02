"""Avatar package providing API routes for managing avatars."""

from .repository import init_app as init_repository
from .routes import avatar_bp

def init_app(app) -> None:
    """Initialise avatar related infrastructure for the Flask app."""

    init_repository(app)


__all__ = ["avatar_bp", "init_app"]