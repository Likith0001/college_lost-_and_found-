from django.contrib.admin.apps import AdminConfig
from django.contrib.auth.apps import AuthConfig
from django.contrib.contenttypes.apps import ContentTypesConfig


class MongoAdminConfig(AdminConfig):
    """Use MongoDB ObjectIds for Django's admin models."""

    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'


class MongoAuthConfig(AuthConfig):
    """Use MongoDB ObjectIds for Django's authentication models."""

    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'


class MongoContentTypesConfig(ContentTypesConfig):
    """Use MongoDB ObjectIds for Django's content-type models."""

    default_auto_field = 'django_mongodb_backend.fields.ObjectIdAutoField'
