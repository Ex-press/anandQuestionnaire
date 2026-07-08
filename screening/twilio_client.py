import logging

from django.conf import settings
from twilio.rest import Client

logger = logging.getLogger(__name__)

_client = None


def get_client():
    global _client
    if _client is None:
        _client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    return _client


def send_sms(to, body):
    """Send an SMS via the Twilio REST API. Returns the message SID, or None on failure."""
    try:
        message = get_client().messages.create(
            to=to,
            from_=settings.TWILIO_FROM_NUMBER,
            body=body,
        )
        logger.info("Sent SMS to %s (sid=%s)", to, message.sid)
        return message.sid
    except Exception:
        logger.exception("Failed to send SMS to %s", to)
        return None
