from django.db import models


class Question(models.Model):
    """An ordered screening question. Editable in the admin; seeded via migration."""

    order = models.PositiveIntegerField(unique=True, help_text="The order in which questions are asked.")
    key = models.SlugField(
        max_length=50, unique=True, help_text="Stable identifier used when recording answers."
    )
    text = models.TextField()
    counts_toward_score = models.BooleanField(
        default=True, help_text="Whether a 'yes' to this question counts toward the screening score."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.order}. {self.text[:60]}"


class Person(models.Model):
    """A person on the roster being screened."""

    name = models.CharField(max_length=200, blank=True, help_text="Leave blank if unknown.")
    phone_number = models.CharField(max_length=32, unique=True, help_text="E.164 format, e.g. +15551234567")
    primary_language = models.CharField(
        max_length=64, default="English", help_text="Language the screening conversation is conducted in."
    )
    notes = models.TextField(blank=True)

    # Consent / opt-in. Under the inbound-keyword model, the person's first
    # inbound SMS is the opt-in and serves as the proof of consent.
    consent_at = models.DateTimeField(
        null=True, blank=True, help_text="When the person opted in (their first inbound message)."
    )
    consent_message_sid = models.CharField(max_length=64, blank=True)
    consent_text = models.TextField(
        blank=True, help_text="The inbound message body that constitutes consent / opt-in."
    )
    opted_out = models.BooleanField(default=False, help_text="Set when the person replies STOP.")
    opted_out_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "phone_number"]

    def __str__(self):
        return f"{self.name or 'Unknown'} ({self.phone_number})"

    @property
    def latest_conversation(self):
        return self.conversations.order_by("-started_at").first()

    @property
    def has_consent(self):
        return self.consent_at is not None and not self.opted_out


class Conversation(models.Model):
    """One screening attempt with a person: its message log and resulting score."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STATUS_CHOICES = [
        (IN_PROGRESS, "In progress"),
        (COMPLETED, "Completed"),
        (ABANDONED, "Abandoned"),
    ]

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="conversations")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Scoring (derived from Answer rows; cached here for easy review/reporting).
    yes_count = models.PositiveSmallIntegerField(default=0)
    screen_positive = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.person} #{self.pk} ({self.status})"

    def score_summary(self):
        if self.status != self.COMPLETED:
            return "In progress"
        if self.screen_positive is True:
            return f"POSITIVE ({self.yes_count} yes)"
        if self.screen_positive is False:
            return f"Negative ({self.yes_count} yes)"
        return f"Complete ({self.yes_count} yes)"

    score_summary.short_description = "Screening score"


class Message(models.Model):
    """A single SMS turn in a conversation (or an internal/staff-generated turn)."""

    USER = "user"
    ASSISTANT = "assistant"
    ROLE_CHOICES = [(USER, "User"), (ASSISTANT, "Assistant")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES)
    body = models.TextField(blank=True)
    internal = models.BooleanField(default=False, help_text="Synthetic turn not sent to/from the person.")
    twilio_sid = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.body[:50]}"


class Answer(models.Model):
    """A recorded answer to one screening question within a conversation."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"
    VALUE_CHOICES = [(YES, "Yes"), (NO, "No"), (UNKNOWN, "Unknown")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.SET_NULL, related_name="answers"
    )
    # Snapshot of the key/text at answer time, so answers survive question edits.
    question_key = models.CharField(max_length=50)
    question_text = models.TextField()
    value = models.CharField(max_length=10, choices=VALUE_CHOICES)
    patient_quote = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("conversation", "question_key")]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.question_key}={self.value}"
