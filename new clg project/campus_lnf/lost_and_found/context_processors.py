from django.conf import settings


def notification_settings(request):
    return {'vapid_public_key': settings.VAPID_PUBLIC_KEY}
