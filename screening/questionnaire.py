"""Scoring/helpers for the screening questionnaire.

Questions live in the database (see the Question model); this module reads them.
The positive-screen rule is: number of "yes" answers (among questions flagged
counts_toward_score) >= settings.SCREEN_POSITIVE_THRESHOLD.
"""
from django.conf import settings

from .models import Question


def active_questions():
    return list(Question.objects.filter(is_active=True).order_by("order"))


def question_keys():
    return list(
        Question.objects.filter(is_active=True).order_by("order").values_list("key", flat=True)
    )


def text_for(key):
    obj = Question.objects.filter(key=key).first()
    return obj.text if obj else key


def positive_threshold():
    return int(getattr(settings, "SCREEN_POSITIVE_THRESHOLD", 1))


def evaluate(answers):
    """Given {question_key: "yes"|"no"|"unknown"}, compute screening state."""
    questions = active_questions()
    keys = [q.key for q in questions]
    scoring_keys = [q.key for q in questions if q.counts_toward_score]
    yes_count = sum(1 for k in scoring_keys if answers.get(k) == "yes")
    remaining = [k for k in keys if not answers.get(k)]
    complete = bool(keys) and not remaining
    threshold = positive_threshold()
    screen_positive = (yes_count >= threshold) if complete else None
    return {
        "yes_count": yes_count,
        "answered_count": len(keys) - len(remaining),
        "total_questions": len(keys),
        "remaining": remaining,
        "complete": complete,
        "screen_positive": screen_positive,
        "threshold": threshold,
    }
