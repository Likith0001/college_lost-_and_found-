from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone


class UserProfile(models.Model):
    """
    One-to-one extension of Django's built-in User.
    Stores campus-specific metadata.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    student_id = models.CharField(max_length=20, unique=True)
    department = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.student_id})"


class DeviceSubscription(models.Model):
    """A browser/device endpoint that can receive campus notifications."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='device_subscriptions')
    endpoint = models.URLField(max_length=2000, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.username} device ({self.endpoint[:40]})'


class Notification(models.Model):
    """Durable notification history for a registered campus device owner."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    item = models.ForeignKey(
        'Item', on_delete=models.SET_NULL, null=True, blank=True, related_name='notifications'
    )
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}: {self.title}'


class Item(models.Model):
    """Represents a lost or found item on campus."""

    class Category(models.TextChoices):
        ELECTRONICS = 'Electronics', 'Electronics'
        DOCUMENTS   = 'Documents/IDs', 'Documents / IDs'
        BOOKS       = 'Books', 'Books'
        CLOTHING    = 'Clothing', 'Clothing'
        OTHERS      = 'Others', 'Others'

    class Status(models.TextChoices):
        LOST     = 'Lost',     'Lost'
        FOUND    = 'Found',    'Found'
        CLAIMED  = 'Claimed',  'Claimed'
        RETURNED = 'Returned', 'Returned'

    title           = models.CharField(max_length=200)
    description     = models.TextField()
    category        = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHERS)
    status          = models.CharField(max_length=10, choices=Status.choices, default=Status.LOST)
    image           = models.ImageField(upload_to='items/', blank=True, null=True)
    campus_location = models.CharField(max_length=200)
    # Set once, when the student submits the lost/found report.
    submitted_at    = models.DateTimeField(default=timezone.now, editable=False)
    updated_at      = models.DateTimeField(auto_now=True)
    reported_by     = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reported_items'
    )
    claimed_by      = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='claimed_items'
    )

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"[{self.status}] {self.title}"

    @property
    def status_badge_class(self):
        return {
            'Lost':     'danger',
            'Found':    'success',
            'Claimed':  'warning',
            'Returned': 'secondary',
        }.get(self.status, 'primary')

    @property
    def category_icon(self):
        return {
            'Electronics':   'bi-cpu',
            'Documents/IDs': 'bi-file-earmark-text',
            'Books':         'bi-book',
            'Clothing':      'bi-bag',
            'Others':        'bi-box-seam',
        }.get(self.category, 'bi-question-circle')


class ClaimRequest(models.Model):
    """Tracks a student's claim on a Found item."""

    class Status(models.TextChoices):
        PENDING  = 'Pending',  'Pending'
        APPROVED = 'Approved', 'Approved'
        REJECTED = 'Rejected', 'Rejected'

    item             = models.ForeignKey(Item, on_delete=models.CASCADE, related_name='claims')
    requested_by     = models.ForeignKey(User, on_delete=models.CASCADE, related_name='claim_requests')
    proof_description = models.TextField(
        help_text='Describe identifying features or proof of ownership.'
    )
    date_requested   = models.DateTimeField(default=timezone.now)
    status           = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING
    )

    class Meta:
        ordering = ['-date_requested']
        # A user can only submit one active claim per item
        unique_together = ('item', 'requested_by')

    def __str__(self):
        return f"Claim by {self.requested_by.username} on '{self.item.title}' [{self.status}]"

    def clean(self):
        """Keep claim records meaningful even when created outside the form."""
        if self.item_id and self.item.status != Item.Status.FOUND:
            raise ValidationError({'item': 'Claims can only be submitted for found items.'})
        if self.item_id and self.requested_by_id == self.item.reported_by_id:
            raise ValidationError({'requested_by': 'You cannot claim your own item report.'})
