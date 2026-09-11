# Campus Lost & Found Portal

A Django backend for campus lost-and-found reporting, claims, and staff moderation.

## Features

- College-email signup, login/logout, and editable student profiles
- Lost/found report creation, search, filtering, image uploads, editing, and safe deletion
- Ownership claims for found items, with duplicate/self-claim protections
- Staff-only review queue: approving a claim marks the item as claimed and automatically rejects competing pending claims
- Responsive phone, tablet, and laptop layouts with live dashboard refreshes every 15 seconds
- Support for a shared managed PostgreSQL database, so all authenticated devices use the same data
- Durable notification history and optional Web Push notifications for registered browsers/devices
- Django admin support and automated workflow tests

## Run locally

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

To review claims, create a staff account with `python manage.py createsuperuser`, then use **Review Claims** from the account menu.

## MongoDB and shared file storage

The app supports MongoDB for shared records and MongoDB GridFS for report
images and profile avatars. GridFS keeps uploads in the same managed database,
so they are available to every deployed application instance.

For local MongoDB, use the example values below (or copy `.env.example` for
reference), set them in PowerShell, and start the database:

```powershell
$env:MONGODB_URI = 'mongodb://campus_app:change-this-local-password@localhost:27017/?authSource=admin'
$env:MONGODB_DB_NAME = 'campus_lnf'
docker compose up -d mongodb
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

For access from other devices, create a MongoDB Atlas deployment and set
`MONGODB_URI` to its connection string and `MONGODB_DB_NAME=campus_lnf` on the
web host. Then run `python manage.py migrate`. Do not commit the Atlas URI or
database password.

## PostgreSQL production configuration

Set these environment variables before deploying:

- `DJANGO_SECRET_KEY` — a unique secret key
- `DJANGO_DEBUG=false`
- `DJANGO_ALLOWED_HOSTS=your-domain.example`
- `DATABASE_URL=postgresql://user:password@host:5432/database?sslmode=require`

Run the test suite with `python manage.py test`.

For shared multi-device access, deploy the project on a public HTTPS host and connect it to MongoDB Atlas (recommended for this configuration) or PostgreSQL. Install the dependencies, set the variables above in the host's environment, run `python manage.py migrate`, and create an admin account. SQLite is retained only as a no-configuration local-development fallback.

In production, the application now refuses to start unless `DATABASE_URL` or
`MONGODB_URI` is configured. This prevents separate devices from accidentally
using separate local SQLite databases. All users, reports, claims, device
registrations, and notifications are then read from the same hosted database.

To move existing local records to hosted PostgreSQL, export the records before
deployment with `python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.Permission > data.json`, point the deployment at the hosted database, run `python manage.py migrate`, and load them with `python manage.py loaddata data.json`.

## Device notifications

Reports remain in the shared database until the owner explicitly deletes them.
After signing in, a user can select **Enable notifications** to register that
browser/device. New reports, claims, and claim/status changes are stored in the
notification history for active students.

To deliver Web Push notifications while the site is closed, configure HTTPS and
these server environment variables:

- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_CLAIMS_EMAIL`, such as `mailto:admin@your-campus.example`

Without VAPID keys, events are still retained in the database and available from
the notification API; only closed-browser Web Push delivery is disabled.
