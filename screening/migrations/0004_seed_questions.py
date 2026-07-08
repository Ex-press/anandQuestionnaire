from django.db import migrations

from screening.default_questions import DEFAULT_QUESTIONS


def seed(apps, schema_editor):
    Question = apps.get_model("screening", "Question")
    for i, item in enumerate(DEFAULT_QUESTIONS, start=1):
        Question.objects.update_or_create(
            key=item["key"],
            defaults={
                "order": i,
                "text": item["text"],
                "counts_toward_score": item.get("counts_toward_score", True),
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    Question = apps.get_model("screening", "Question")
    Question.objects.filter(key__in=[item["key"] for item in DEFAULT_QUESTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("screening", "0003_question_remove_conversation_entry_criterion_met_and_more"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
