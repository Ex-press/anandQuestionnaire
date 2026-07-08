import logging
import threading

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from twilio.request_validator import RequestValidator

from . import conversation as convo
from .models import Conversation, Message, Person

logger = logging.getLogger(__name__)

# Standard carrier opt-out / opt-in keywords (Twilio also handles these itself).
STOP_KEYWORDS = {"stop", "stopall", "stop all", "unsubscribe", "cancel", "end", "quit"}
START_KEYWORDS = {"start", "unstop", "yes"}

_EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twiml_response():
    return HttpResponse(_EMPTY_TWIML, content_type="text/xml")


def _signature_ok(request):
    if not settings.TWILIO_VALIDATE_SIGNATURE:
        return True
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = settings.TWILIO_WEBHOOK_BASE_URL.rstrip("/") + request.get_full_path()
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(url, request.POST.dict(), signature)


def _get_active_conversation(person):
    conv = person.conversations.filter(status=Conversation.IN_PROGRESS).order_by("-started_at").first()
    if conv is None:
        conv = Conversation.objects.create(person=person)
    return conv


@csrf_exempt
@require_POST
def sms_webhook(request):
    """Inbound SMS webhook. Logs the message, then processes the reply asynchronously."""
    if not _signature_ok(request):
        logger.warning("Rejected webhook with invalid Twilio signature")
        return HttpResponseForbidden("invalid signature")

    from_number = request.POST.get("From", "").strip()
    body = request.POST.get("Body", "").strip()
    message_sid = request.POST.get("MessageSid", "").strip()

    if not from_number:
        return HttpResponse(status=400)

    keyword = body.lower()
    person, _ = Person.objects.get_or_create(phone_number=from_number)

    # Idempotency: Twilio retries webhooks; ignore a message_sid we've already stored.
    if message_sid and Message.objects.filter(twilio_sid=message_sid, role=Message.USER).exists():
        return _twiml_response()

    # Opt-out (STOP). Twilio also blocks further sends at the carrier level.
    if keyword in STOP_KEYWORDS:
        person.opted_out = True
        person.opted_out_at = timezone.now()
        person.save(update_fields=["opted_out", "opted_out_at"])
        logger.info("Opt-out (STOP) from %s", from_number)
        return _twiml_response()

    # Previously opted out: only a START keyword re-engages; otherwise stay silent.
    if person.opted_out:
        if keyword in START_KEYWORDS:
            person.opted_out = False
            person.opted_out_at = None
            person.save(update_fields=["opted_out", "opted_out_at"])
        else:
            logger.info("Ignoring message from opted-out %s", from_number)
            return _twiml_response()

    # Record consent on first opt-in — this inbound message IS the proof of consent.
    if person.consent_at is None:
        person.consent_at = timezone.now()
        person.consent_message_sid = message_sid
        person.consent_text = body
        person.save(update_fields=["consent_at", "consent_message_sid", "consent_text"])

    conversation = _get_active_conversation(person)
    Message.objects.create(
        conversation=conversation, role=Message.USER, body=body, twilio_sid=message_sid
    )

    # Reply asynchronously so we return well within Twilio's webhook timeout.
    threading.Thread(target=convo.handle_inbound, args=(conversation.id,), daemon=True).start()
    return _twiml_response()


@require_GET
def index(request):
    html = (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        "<title>Anand epilepsy screening</title>"
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "max-width:560px;margin:3rem auto;padding:0 1rem;color:#1b1b1b}"
        "a{color:#1558d6}</style></head><body>"
        "<h1>Anand epilepsy screening</h1>"
        "<p>SMS-based epilepsy screening service.</p>"
        "<ul>"
        "<li><a href='/admin/'>Staff admin</a> &mdash; roster, conversations, scores</li>"
        "<li><a href='/consent'>Consent lookup</a> &mdash; proof of opt-in by phone number</li>"
        "</ul></body></html>"
    )
    return HttpResponse(html)


@require_GET
def health(request):
    return HttpResponse("ok")


def _normalize_phone(raw):
    # In query strings, "+" decodes to a space, so "?phoneNumber=+1555..." arrives
    # as " 1555...". Strip spaces and re-add the leading "+".
    digits = (raw or "").strip().replace(" ", "")
    if digits and not digits.startswith("+"):
        digits = "+" + digits
    return digits


@require_GET
def consent_proof(request):
    """Public proof-of-consent lookup: /consent?phoneNumber=+12345678901"""
    phone = _normalize_phone(request.GET.get("phoneNumber", ""))
    person = Person.objects.filter(phone_number=phone).first() if phone else None
    return render(
        request,
        "screening/consent.html",
        {"queried": bool(phone), "phone": phone, "person": person},
    )
