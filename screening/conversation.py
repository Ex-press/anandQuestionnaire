"""The Claude-driven conversation engine.

Each turn, Claude sees the full SMS history plus a dynamic system prompt that
embeds the questionnaire (read from the DB) and the answers recorded so far.
Claude decides the next message and calls the `record_answer` tool to log answers.
"""
import json
import logging

import anthropic
from django.conf import settings
from django.db import connection
from django.utils import timezone

from . import questionnaire as q
from .models import Answer, Conversation, Message, Question
from .twilio_client import send_sms

logger = logging.getLogger(__name__)

# A synthetic user turn used to kick off a staff-initiated screening.
START_SENTINEL = "[screening started by staff]"
MAX_TOOL_ITERATIONS = 14

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def build_record_answer_tool():
    """Built per call so the question_key enum reflects the current DB questions."""
    return {
        "name": "record_answer",
        "description": (
            "Record the person's answer to one screening question. Call this every time you can "
            "determine an answer from what the person said. Call it multiple times if they answer "
            "several questions at once."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question_key": {
                    "type": "string",
                    "enum": q.question_keys(),
                    "description": "Which screening question this answers.",
                },
                "value": {
                    "type": "string",
                    "enum": ["yes", "no", "unknown"],
                    "description": "The quantitative answer to the question.",
                },
                "patient_quote": {
                    "type": "string",
                    "description": "A short paraphrase or quote of what the person said, in their own words.",
                },
            },
            "required": ["question_key", "value", "patient_quote"],
            "additionalProperties": False,
        },
    }


def _thinking_param():
    if "haiku" in settings.ANTHROPIC_MODEL.lower():
        return None
    return {"type": "adaptive"}


def build_system_prompt(conversation):
    language = (conversation.person.primary_language or "English").strip() or "English"
    questions = q.active_questions()
    qlist = "\n".join(f'  - [{item.key}] {item.text}' for item in questions)

    answers = {a.question_key: a for a in conversation.answers.all()}
    progress_lines = []
    for item in questions:
        a = answers.get(item.key)
        progress_lines.append(
            f'  - [{item.key}] -> '
            + (f'{a.value} ("{a.patient_quote}")' if a else "not yet answered")
        )
    progress = "\n".join(progress_lines)
    res = q.evaluate({k: a.value for k, a in answers.items()})
    if res["complete"]:
        status = "COMPLETE — send a brief neutral closing message."
    else:
        status = "in progress; next, ask the next unanswered question in order: " + (
            ", ".join(res["remaining"]) or "n/a"
        )

    return f"""You are a warm, plain-spoken health worker conducting an epilepsy screening \
questionnaire by SMS text message.

LANGUAGE: Conduct the ENTIRE conversation in {language}. Every message you send must be written in {language}.

You are texting a member of the public. The questions are about whether the person has ever had \
seizure-like episodes — this could be the texter themselves or someone they care for. Mirror whichever they use.

HOW TO RUN THE SCREENING:
- On your FIRST reply in the conversation, send a brief, friendly introduction: say this is a short, \
voluntary health screening about seizure-like episodes, and include the line "Reply STOP to opt out." \
Then ask the first question. (If the latest user message is exactly "{START_SENTINEL}", treat it the same \
way and never repeat that signal back to the person.)
- Ask ONE question at a time, IN ORDER, and wait for the reply.
- Use simple, non-clinical words. Keep every message under ~300 characters (it is an SMS).
- Be kind and non-judgmental. NEVER diagnose, score, or interpret results for the person.
- Whenever you can determine an answer, call the record_answer tool (question_key, value yes/no/unknown, \
and a short patient_quote). Then continue to the next question.
- If a reply is ambiguous, ask a brief clarifying question instead of guessing.
- When the tool result says the screening is COMPLETE, send a short, neutral closing message thanking them \
and suggesting they share their answers with a doctor or clinic. Do not tell them the result.

THE QUESTIONS (ask in this order):
{qlist}

PROGRESS SO FAR (already recorded — do not re-ask these):
{progress}

STATUS: {status}
"""


def record_answer(conversation, data):
    key = data["question_key"]
    value = data["value"]
    quote = data.get("patient_quote", "")
    question = Question.objects.filter(key=key).first()
    Answer.objects.update_or_create(
        conversation=conversation,
        question_key=key,
        defaults={
            "question": question,
            "question_text": q.text_for(key),
            "value": value,
            "patient_quote": quote,
        },
    )
    answers = {a.question_key: a.value for a in conversation.answers.all()}
    res = q.evaluate(answers)
    return {
        "recorded": key,
        "value": value,
        "complete": res["complete"],
        "answered": res["answered_count"],
        "total": res["total_questions"],
        "remaining_questions": res["remaining"],
        "next_step": (
            "Screening complete — send a brief neutral closing message in the person's language."
            if res["complete"]
            else "Ask the next unanswered question."
        ),
    }


def _run_engine(conversation):
    history = []
    for m in conversation.messages.order_by("created_at"):
        if not m.body.strip():
            continue
        role = "assistant" if m.role == Message.ASSISTANT else "user"
        history.append({"role": role, "content": m.body})
    if not history:
        history.append({"role": "user", "content": START_SENTINEL})

    create_kwargs = dict(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
        system=build_system_prompt(conversation),
        tools=[build_record_answer_tool()],
        messages=history,
    )
    thinking = _thinking_param()
    if thinking:
        create_kwargs["thinking"] = thinking

    client = get_client()
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(**create_kwargs)
        if response.stop_reason == "tool_use":
            create_kwargs["messages"].append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use" and block.name == "record_answer":
                    out = record_answer(conversation, block.input)
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out)}
                    )
            create_kwargs["messages"].append({"role": "user", "content": results})
            continue
        return "".join(b.text for b in response.content if b.type == "text").strip()

    logger.warning("Engine hit max tool iterations for conversation %s", conversation.id)
    return ""


def _finalize(conversation):
    answers = {a.question_key: a.value for a in conversation.answers.all()}
    res = q.evaluate(answers)
    conversation.yes_count = res["yes_count"]
    if res["complete"]:
        if conversation.status != Conversation.COMPLETED:
            conversation.completed_at = timezone.now()
        conversation.status = Conversation.COMPLETED
        conversation.screen_positive = res["screen_positive"]
    conversation.save()


def handle_inbound(conversation_id):
    """Run one engine turn, send the reply, and update the score.

    Safe to call from a background thread; closes the DB connection when done.
    """
    try:
        conversation = Conversation.objects.select_related("person").get(id=conversation_id)
        reply = _run_engine(conversation)
        if reply:
            message = Message.objects.create(
                conversation=conversation, role=Message.ASSISTANT, body=reply
            )
            sid = send_sms(conversation.person.phone_number, reply)
            if sid:
                message.twilio_sid = sid
                message.save(update_fields=["twilio_sid"])
        _finalize(conversation)
    except Exception:
        logger.exception("handle_inbound failed for conversation %s", conversation_id)
    finally:
        connection.close()


def initiate(person):
    """Staff/test-initiated screening (outbound). Use only with prior consent."""
    conversation = Conversation.objects.create(person=person)
    Message.objects.create(
        conversation=conversation, role=Message.USER, body=START_SENTINEL, internal=True
    )
    handle_inbound(conversation.id)
    return conversation
