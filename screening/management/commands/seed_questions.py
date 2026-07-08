from django.core.management.base import BaseCommand

from screening.default_questions import DEFAULT_QUESTIONS
from screening.models import Question


class Command(BaseCommand):
    help = "Seed or refresh the screening questions from default_questions.py (idempotent)."

    def handle(self, *args, **options):
        for i, item in enumerate(DEFAULT_QUESTIONS, start=1):
            obj, created = Question.objects.update_or_create(
                key=item["key"],
                defaults={
                    "order": i,
                    "text": item["text"],
                    "counts_toward_score": item.get("counts_toward_score", True),
                    "is_active": True,
                },
            )
            self.stdout.write(("created " if created else "updated ") + f"{obj.order}. {obj.key}")
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(DEFAULT_QUESTIONS)} questions."))
