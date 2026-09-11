from django.apps import AppConfig
from django.conf import settings


class LostAndFoundConfig(AppConfig):
    default_auto_field = (
        'django_mongodb_backend.fields.ObjectIdAutoField'
        if settings.MONGODB_URI else 'django.db.models.BigAutoField'
    )
    name = 'lost_and_found'
    verbose_name = 'Campus Lost & Found'
