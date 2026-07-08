# anand.artiswrong.com — Anand epilepsy SMS screening

A Twilio SMS app with a Django backend that administers the **Anand epilepsy
screening questionnaire** over text, driven by the Claude API.

- A **roster** of people to screen (`Person`: name, phone, primary language).
- Claude conducts a back-and-forth SMS conversation **in the person's language**,
  asking the stem question and (if met) the six feature questions, and logging
  each answer (qualitative quote + yes/no/unknown) via a `record_answer` tool.
- Scoring: stem "yes" **and** ≥4 of 6 feature questions "yes" → screen positive.
- Conversation logs and scores are reviewable in the Django admin.

## Layout

```
anand/            Django project (settings, urls, wsgi)
screening/        the app
  questionnaire.py  the Anand questions + scoring rule
  models.py         Person, Conversation, Message, Answer
  conversation.py   Claude-driven engine (record_answer tool, async send)
  twilio_client.py  outbound SMS via Twilio REST API
  views.py          inbound webhook (signature-validated, async reply)
  admin.py          roster + conversation review, "start screening" action
deploy/           gunicorn service, Apache vhost, deploy README
```

See `deploy/README.md` to set up the venv, run migrations, and configure
Apache + Twilio.
