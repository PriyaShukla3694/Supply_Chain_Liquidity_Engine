from datetime import date

from app.core.config import settings


def business_today() -> date:
    """Return the configured business date, or today's real date."""
    return settings.REFERENCE_DATE or date.today()