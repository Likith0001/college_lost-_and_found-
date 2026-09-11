"""Django file storage backed by MongoDB GridFS."""

from io import BytesIO
from urllib.parse import quote

from django.conf import settings
from django.core.files.base import File
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from gridfs import GridFS
from pymongo import MongoClient


@deconstructible
class GridFSStorage(Storage):
    """Store uploaded report images and avatars in the configured MongoDB database."""

    def __init__(self):
        if not settings.MONGODB_URI:
            raise RuntimeError('GridFSStorage requires the MONGODB_URI setting.')
        self.client = MongoClient(settings.MONGODB_URI)
        self.fs = GridFS(self.client[settings.MONGODB_DB_NAME])

    def _file_document(self, name):
        return self.fs.find_one({'filename': name})

    def _open(self, name, mode='rb'):
        document = self._file_document(name)
        if not document:
            raise FileNotFoundError(name)
        buffer = BytesIO()
        buffer.write(self.fs.get(document._id).read())
        buffer.seek(0)
        return File(buffer, name=name)

    def _save(self, name, content):
        name = self.get_available_name(name)
        self.fs.put(content, filename=name,
                    metadata={'content_type': getattr(content, 'content_type', None)})
        return name

    def delete(self, name):
        for document in self.fs.find({'filename': name}):
            self.fs.delete(document._id)

    def exists(self, name):
        return self._file_document(name) is not None

    def size(self, name):
        document = self._file_document(name)
        if not document:
            raise FileNotFoundError(name)
        return document.length

    def url(self, name):
        return f'{settings.MEDIA_URL}{quote(name, safe="/")}'
