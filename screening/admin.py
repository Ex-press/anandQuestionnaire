from django.contrib import admin

from .models import Answer, Conversation, Message, Person, Question


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "key", "text", "counts_toward_score", "is_active")
    list_display_links = ("key",)
    list_editable = ("order", "counts_toward_score", "is_active")
    ordering = ("order",)


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = ("role", "body", "internal", "twilio_sid", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ("question_key", "question_text", "value", "patient_quote", "updated_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class ConversationInline(admin.TabularInline):
    model = Conversation
    extra = 0
    fields = ("id", "status", "score_summary", "started_at", "completed_at")
    readonly_fields = fields
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def score_summary(self, obj):
        return obj.score_summary()


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "phone_number",
        "primary_language",
        "consent",
        "opted_out",
        "latest_score",
        "created_at",
    )
    search_fields = ("name", "phone_number")
    list_filter = ("primary_language", "opted_out")
    inlines = [ConversationInline]
    readonly_fields = (
        "consent_at",
        "consent_message_sid",
        "consent_text",
        "opted_out_at",
        "created_at",
        "updated_at",
    )

    @admin.display(boolean=True, description="Consent")
    def consent(self, obj):
        return obj.has_consent

    @admin.display(description="Latest score")
    def latest_score(self, obj):
        conv = obj.latest_conversation
        return conv.score_summary() if conv else "—"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "person",
        "status",
        "score_summary",
        "yes_count",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "screen_positive")
    search_fields = ("person__name", "person__phone_number")
    readonly_fields = (
        "person",
        "status",
        "yes_count",
        "screen_positive",
        "started_at",
        "updated_at",
        "completed_at",
    )
    inlines = [AnswerInline, MessageInline]

    @admin.display(description="Screening score")
    def score_summary(self, obj):
        return obj.score_summary()
