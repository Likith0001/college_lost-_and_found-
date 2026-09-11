from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed, JsonResponse
import json
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings
from mimetypes import guess_type

from .models import DeviceSubscription, Item, ClaimRequest, Notification, UserProfile
from .forms import (
    CampusSignupForm, ItemForm, ItemStatusUpdateForm,
    ClaimRequestForm, ItemFilterForm, ProfileForm,
)


def _send_push(subscription, title, message, item=None):
    """Send best-effort Web Push when VAPID settings and pywebpush are available."""
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        return
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return

    try:
        webpush(
            subscription_info={
                'endpoint': subscription.endpoint,
                'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
            },
            data=json.dumps({
                'title': title,
                'message': message,
                'url': f'/item/{item.pk}/' if item else '/',
            }),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={'sub': settings.VAPID_CLAIMS_EMAIL},
        )
    except WebPushException:
        # A stale browser subscription should not be retried forever.
        subscription.delete()


def notify_campus(title, message, item=None, exclude_user_id=None):
    """Persist a notification for every active student and push to each device."""
    from django.contrib.auth.models import User

    users = User.objects.filter(is_active=True)
    if exclude_user_id:
        users = users.exclude(pk=exclude_user_id)
    notifications = [
        Notification(user=user, title=title, message=message, item=item)
        for user in users
    ]
    Notification.objects.bulk_create(notifications)
    for subscription in DeviceSubscription.objects.filter(user__in=users).select_related('user'):
        _send_push(subscription, title, message, item)


@login_required
def device_subscription_view(request):
    """Register or remove the current browser/device for Web Push."""
    if request.method == 'DELETE':
        try:
            endpoint = json.loads(request.body).get('endpoint', '')
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)
        DeviceSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return JsonResponse({'registered': False})
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST', 'DELETE'])
    try:
        payload = json.loads(request.body)
        endpoint = payload['endpoint']
        keys = payload['keys']
        if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
            raise KeyError
    except (KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'A valid push subscription is required.'}, status=400)
    DeviceSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            'user': request.user,
            'p256dh': keys['p256dh'],
            'auth': keys['auth'],
        },
    )
    return JsonResponse({'registered': True})


@login_required
def notifications_view(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        return JsonResponse({'marked_read': True})
    notifications = Notification.objects.filter(user=request.user)[:30]
    return JsonResponse({
        'notifications': [
            {
                'title': notification.title,
                'message': notification.message,
                'url': f'/item/{notification.item_id}/' if notification.item_id else '/',
                'created_at': notification.created_at.isoformat(),
                'read': notification.read_at is not None,
            }
            for notification in notifications
        ]
    })


def service_worker_view(request):
        """Serve the worker from the site root so its push scope covers the portal."""
        return HttpResponse(
                """self.addEventListener('push', event => {
    const data = event.data ? event.data.json() : {};
    event.waitUntil(self.registration.showNotification(data.title || 'Campus Lost & Found', {
        body: data.message || 'There is a new campus update.',
        icon: '/static/lost_and_found/icon-192.png',
        data: { url: data.url || '/' }
    }));
});
self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil(clients.openWindow(event.notification.data.url || '/'));
});""",
                content_type='application/javascript',
        )


def gridfs_media_view(request, name):
    """Serve a GridFS upload when MongoDB storage is enabled."""
    if not settings.MONGODB_URI:
        raise Http404
    try:
        uploaded_file = Item._meta.get_field('image').storage.open(name)
    except FileNotFoundError:
        raise Http404
    content_type, _ = guess_type(name)
    return FileResponse(uploaded_file, content_type=content_type or 'application/octet-stream')


# ── Authentication ────────────────────────────────────────────────────────────

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = CampusSignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f'Welcome, {user.first_name}! Your account has been created.')
        return redirect('dashboard')

    return render(request, 'lost_and_found/signup.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        messages.success(request, f'Welcome back, {user.first_name}!')
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return redirect(next_url)
        return redirect('dashboard')

    return render(request, 'lost_and_found/login.html', {'form': form})


def logout_view(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('login')


# ── Dashboard ─────────────────────────────────────────────────────────────────

@login_required
def dashboard_view(request):
    filter_form = ItemFilterForm(request.GET or None)
    items = Item.objects.select_related('reported_by').all()

    if filter_form.is_valid():
        q        = filter_form.cleaned_data.get('q', '')
        category = filter_form.cleaned_data.get('category', '')
        status   = filter_form.cleaned_data.get('status', '')

        if q:
            items = items.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(campus_location__icontains=q)
            )
        if category:
            items = items.filter(category=category)
        if status:
            items = items.filter(status=status)

    # Split for hero stats
    lost_count    = Item.objects.filter(status='Lost').count()
    found_count   = Item.objects.filter(status='Found').count()
    claimed_count = Item.objects.filter(status__in=['Claimed', 'Returned']).count()

    paginator = Paginator(items, 9)
    page_obj  = paginator.get_page(request.GET.get('page'))
    latest_update = Item.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()

    return render(request, 'lost_and_found/dashboard.html', {
        'filter_form':  filter_form,
        'page_obj':     page_obj,
        'lost_count':   lost_count,
        'found_count':  found_count,
        'claimed_count': claimed_count,
        'latest_update': latest_update.isoformat() if latest_update else '',
    })


@login_required
def item_version_view(request):
    """Small polling endpoint used to refresh dashboards across devices."""
    latest_update = Item.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()
    return JsonResponse({'version': latest_update.isoformat() if latest_update else ''})


# ── Item CRUD ─────────────────────────────────────────────────────────────────

@login_required
def item_report_view(request):
    """Create a new Lost or Found item report."""
    form = ItemForm(request.POST or None, request.FILES or None, is_new=True)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.reported_by = request.user
        item.save()
        notify_campus(
            'New campus item reported',
            f'{item.title} was reported as {item.status.lower()} near {item.campus_location}.',
            item=item,
            exclude_user_id=request.user.pk,
        )
        messages.success(request, 'Item reported successfully!')
        return redirect('item_detail', pk=item.pk)

    return render(request, 'lost_and_found/item_form.html', {
        'form':  form,
        'title': 'Report an Item',
    })


@login_required
def item_detail_view(request, pk):
    item = get_object_or_404(Item, pk=pk)
    claims       = item.claims.select_related('requested_by').all()
    user_claimed = claims.filter(requested_by=request.user).first()

    # Owner can update status inline
    status_form = None
    if item.reported_by == request.user:
        status_form = ItemStatusUpdateForm(request.POST or None, instance=item)
        if request.method == 'POST' and 'update_status' in request.POST:
            if status_form.is_valid():
                new_status = status_form.cleaned_data['status']
                with transaction.atomic():
                    locked_item = Item.objects.select_for_update().get(pk=item.pk)
                    locked_item.status = new_status
                    locked_item.save(update_fields=['status', 'updated_at'])
                    if new_status == Item.Status.RETURNED:
                        ClaimRequest.objects.filter(
                            item=locked_item, status=ClaimRequest.Status.PENDING
                        ).update(status=ClaimRequest.Status.REJECTED)
                notify_campus(
                    'Item status updated',
                    f'{locked_item.title} is now marked {locked_item.status.lower()}.',
                    item=locked_item,
                    exclude_user_id=request.user.pk,
                )
                messages.success(request, 'Item status updated.')
                return redirect('item_detail', pk=pk)
            # A bound ModelForm can copy invalid posted values to its instance.
            # Reload it so the page always reflects the persisted item state.
            item.refresh_from_db()
            messages.error(request, 'That status change is not allowed.')

    return render(request, 'lost_and_found/item_detail.html', {
        'item':         item,
        'claims':       claims,
        'user_claimed': user_claimed,
        'status_form':  status_form,
    })


@login_required
def item_edit_view(request, pk):
    item = get_object_or_404(Item, pk=pk, reported_by=request.user)
    form = ItemForm(request.POST or None, request.FILES or None, instance=item)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Item updated successfully.')
        return redirect('item_detail', pk=pk)

    return render(request, 'lost_and_found/item_form.html', {
        'form':  form,
        'title': 'Edit Item',
        'item':  item,
    })


@login_required
def item_delete_view(request, pk):
    """Allow reporters to remove an open report they created."""
    item = get_object_or_404(Item, pk=pk, reported_by=request.user)
    if item.status in (Item.Status.CLAIMED, Item.Status.RETURNED):
        messages.error(request, 'Claimed or returned item reports are retained for accountability.')
        return redirect('item_detail', pk=item.pk)
    if request.method == 'POST':
        item.delete()
        messages.success(request, 'Item report deleted.')
        return redirect('my_items')
    return render(request, 'lost_and_found/item_confirm_delete.html', {'item': item})


@login_required
def my_items_view(request):
    reported = Item.objects.filter(reported_by=request.user)
    claims   = ClaimRequest.objects.filter(requested_by=request.user).select_related('item')
    return render(request, 'lost_and_found/my_items.html', {
        'reported': reported,
        'claims':   claims,
    })


@login_required
def profile_view(request):
    """Create a missing legacy profile, then let the user edit it safely."""
    profile, _ = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'student_id': request.user.username},
    )

    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your profile has been updated.')
        return redirect('profile')
    return render(request, 'lost_and_found/profile.html', {'form': form, 'profile': profile})


# ── Claim ─────────────────────────────────────────────────────────────────────

@login_required
def claim_item_view(request, pk):
    item = get_object_or_404(Item, pk=pk, status='Found')

    # Prevent self-claiming own item
    if item.reported_by == request.user:
        messages.warning(request, "You can't claim your own report.")
        return redirect('item_detail', pk=pk)

    # Prevent duplicate claims
    existing = ClaimRequest.objects.filter(item=item, requested_by=request.user).first()
    if existing:
        messages.info(request, f'You already submitted a claim (status: {existing.status}).')
        return redirect('item_detail', pk=pk)

    form = ClaimRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        claim = form.save(commit=False)
        claim.item         = item
        claim.requested_by = request.user
        try:
            claim.full_clean()
            claim.save()
        except (IntegrityError, ValueError):
            messages.error(request, 'This item is no longer available to claim.')
            return redirect('item_detail', pk=pk)
        notify_campus(
            'New claim request',
            f'{claim.requested_by.get_full_name() or claim.requested_by.username} claimed {item.title}.',
            item=item,
            exclude_user_id=request.user.pk,
        )
        messages.success(request, 'Claim submitted! Campus authorities will review it.')
        return redirect('item_detail', pk=pk)

    return render(request, 'lost_and_found/claim_form.html', {
        'form': form,
        'item': item,
    })


staff_required = user_passes_test(lambda user: user.is_active and user.is_staff)


@staff_required
def claim_review_list_view(request):
    """Staff work queue for reviewing pending ownership claims."""
    claims = ClaimRequest.objects.filter(status=ClaimRequest.Status.PENDING).select_related(
        'item', 'requested_by', 'item__reported_by'
    )
    return render(request, 'lost_and_found/claim_review_list.html', {'claims': claims})


@staff_required
def claim_decision_view(request, pk, decision):
    """Approve or reject one pending claim and synchronise its item state."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])
    if decision not in {'approve', 'reject'}:
        return HttpResponseNotAllowed(['POST'])

    with transaction.atomic():
        claim = get_object_or_404(
            ClaimRequest.objects.select_for_update().select_related('item'),
            pk=pk,
        )
        item = Item.objects.select_for_update().get(pk=claim.item_id)
        if claim.status != ClaimRequest.Status.PENDING:
            messages.warning(request, 'That claim has already been reviewed.')
        elif decision == 'approve':
            if item.status != Item.Status.FOUND:
                messages.error(request, 'Only claims for currently found items can be approved.')
            else:
                claim.status = ClaimRequest.Status.APPROVED
                claim.save(update_fields=['status'])
                ClaimRequest.objects.filter(
                    item=item, status=ClaimRequest.Status.PENDING
                ).exclude(pk=claim.pk).update(status=ClaimRequest.Status.REJECTED)
                item.status = Item.Status.CLAIMED
                item.claimed_by = claim.requested_by
                item.save(update_fields=['status', 'claimed_by', 'updated_at'])
                notify_campus(
                    'Claim approved',
                    f'The claim for {item.title} was approved.',
                    item=item,
                    exclude_user_id=request.user.pk,
                )
                messages.success(request, f"Approved {claim.requested_by.get_full_name() or claim.requested_by.username}'s claim.")
        else:
            claim.status = ClaimRequest.Status.REJECTED
            claim.save(update_fields=['status'])
            notify_campus(
                'Claim rejected',
                f'The claim for {item.title} was rejected.',
                item=item,
                exclude_user_id=request.user.pk,
            )
            messages.success(request, 'Claim rejected.')
    return redirect('claim_review_list')
