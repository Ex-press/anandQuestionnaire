# Deploying anand.artiswrong.com

Serving model: **gunicorn** (127.0.0.1:8011) behind an **Apache** reverse proxy
(matches the existing `amanuensis.artiswrong.com` pattern). Inbound Twilio SMS
hits `/sms/webhook/`; replies are sent asynchronously via the Twilio REST API.

## 1. App setup (no sudo)

```bash
cd /home/japhy/anand.artiswrong.com
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

# Generate a Django secret key and write it into .env:
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print('DJANGO_SECRET_KEY='+g())"
# ...paste the result over the DJANGO_SECRET_KEY line in .env

# Fill in .env: ANTHROPIC_API_KEY and TWILIO_FROM_NUMBER (Twilio SID/token already set).

.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
```

Quick local smoke test:

```bash
.venv/bin/gunicorn anand.wsgi:application --bind 127.0.0.1:8011
# then in another shell: curl http://127.0.0.1:8011/sms/health/  -> "ok"
```

## 2. systemd service (needs sudo)

```bash
sudo cp deploy/gunicorn-anand.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gunicorn-anand
sudo systemctl status gunicorn-anand
```

## 3. Apache vhost + TLS (needs sudo)

```bash
sudo cp deploy/anand.artiswrong.com.conf /etc/apache2/sites-available/
sudo a2enmod proxy proxy_http headers
sudo a2ensite anand.artiswrong.com
sudo apache2ctl configtest
sudo systemctl reload apache2
sudo certbot --apache -d anand.artiswrong.com
```

After certbot, add `RequestHeader set X-Forwarded-Proto "https"` to the generated
`anand.artiswrong.com-le-ssl.conf` and reload Apache.

## 4. Twilio configuration

In the Twilio console, set the messaging webhook for your number to:

```
https://anand.artiswrong.com/sms/webhook/    (HTTP POST)
```

Consent model is **inbound keyword opt-in**: a person texts the number first
(their inbound message is logged as proof of consent on the `Person` record), and
the screening begins automatically. Replying **STOP** opts out; **START** re-opts-in.
Review rosters, consent status, conversation logs, and scores in the admin (`/admin/`).

## Notes / upgrade path

- **Rotate the Twilio auth token** once configured — it was shared in plaintext.
- Background-thread replies are fine for low volume. For higher throughput or
  retry guarantees, move `handle_inbound` to Celery/RQ.
- DB is sqlite; switch `DATABASES` to MySQL (the server already runs it) for scale.
