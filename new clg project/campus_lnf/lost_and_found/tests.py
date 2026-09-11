from django.contrib.auth.models import User
from django.http import Http404
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from .forms import CampusSignupForm, ItemForm, ItemStatusUpdateForm
from .models import ClaimRequest, DeviceSubscription, Item, Notification, UserProfile
from .views import item_delete_view


class PortalWorkflowTests(TestCase):
    def make_user(self, username, staff=False):
        user = User.objects.create_user(
            username=username,
            email=f'{username}@campus.ac.in',
            password='Strong-password-123',
            first_name=username.title(),
            is_staff=staff,
        )
        UserProfile.objects.create(user=user, student_id=f'ID-{username}')
        return user

    def make_item(self, reporter, status=Item.Status.FOUND):
        return Item.objects.create(
            title='Blue backpack',
            description='A blue backpack with a small keychain.',
            category=Item.Category.OTHERS,
            status=status,
            campus_location='Library',
            reported_by=reporter,
        )

    def test_signup_creates_a_profile_and_logs_the_student_in(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newstudent',
            'first_name': 'New',
            'last_name': 'Student',
            'email': 'newstudent@campus.ac.in',
            'student_id': 'CSE-001',
            'department': 'Computer Science',
            'phone': '9876543210',
            'password1': 'Strong-password-123',
            'password2': 'Strong-password-123',
        })
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.assertTrue(UserProfile.objects.filter(student_id='CSE-001').exists())

    def test_signup_rejects_unapproved_email_domain(self):
        form = CampusSignupForm({
            'username': 'outside', 'first_name': 'Outside', 'last_name': 'User',
            'email': 'outside@example.com', 'student_id': 'CSE-002',
            'password1': 'Strong-password-123', 'password2': 'Strong-password-123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertFalse(User.objects.filter(username='outside').exists())

    def test_reporter_cannot_set_claimed_status_directly(self):
        reporter = self.make_user('reporter')
        item = self.make_item(reporter, Item.Status.FOUND)
        form = ItemStatusUpdateForm({
            'update_status': '1', 'status': Item.Status.CLAIMED,
        }, instance=item)
        self.assertFalse(form.is_valid())
        item.refresh_from_db()
        self.assertEqual(item.status, Item.Status.FOUND)

    def test_reporter_cannot_set_claimed_status_via_edit_form(self):
        reporter = self.make_user('reporter')
        item = self.make_item(reporter, Item.Status.FOUND)
        form = ItemForm({
            'title': item.title,
            'description': item.description,
            'category': item.category,
            'status': Item.Status.CLAIMED,
            'campus_location': item.campus_location,
        }, instance=item)
        self.assertFalse(form.is_valid())

    def test_staff_approval_claims_item_and_rejects_other_pending_claims(self):
        reporter = self.make_user('reporter')
        claimant_one = self.make_user('claimantone')
        claimant_two = self.make_user('claimanttwo')
        staff = self.make_user('staff', staff=True)
        item = self.make_item(reporter)
        first = ClaimRequest.objects.create(
            item=item, requested_by=claimant_one, proof_description='My initials are inside.'
        )
        second = ClaimRequest.objects.create(
            item=item, requested_by=claimant_two, proof_description='I have a receipt.'
        )
        self.client.force_login(staff)
        response = self.client.post(reverse('claim_decision', args=[first.pk, 'approve']))
        self.assertRedirects(response, reverse('claim_review_list'), fetch_redirect_response=False)
        item.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(item.status, Item.Status.CLAIMED)
        self.assertEqual(item.claimed_by, claimant_one)
        self.assertEqual(first.status, ClaimRequest.Status.APPROVED)
        self.assertEqual(second.status, ClaimRequest.Status.REJECTED)

    def test_only_staff_can_review_claims(self):
        student = self.make_user('student')
        self.client.force_login(student)
        response = self.client.get(reverse('claim_review_list'))
        self.assertEqual(response.status_code, 302)

    def test_open_report_can_be_deleted_only_by_its_reporter(self):
        reporter = self.make_user('reporter')
        other_user = self.make_user('other')
        item = self.make_item(reporter)
        request = RequestFactory().post(reverse('item_delete', args=[item.pk]))
        request.user = other_user
        with self.assertRaises(Http404):
            item_delete_view.__wrapped__(request, pk=item.pk)
        self.client.force_login(reporter)
        response = self.client.post(reverse('item_delete', args=[item.pk]))
        self.assertRedirects(response, reverse('my_items'), fetch_redirect_response=False)
        self.assertFalse(Item.objects.filter(pk=item.pk).exists())

    def test_logout_requires_post(self):
        user = self.make_user('student')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(
            self.client.post(reverse('logout')), reverse('login'), fetch_redirect_response=False
        )

    def test_item_version_endpoint_exposes_the_latest_change_for_live_refresh(self):
        reporter = self.make_user('reporter')
        item = self.make_item(reporter)
        self.client.force_login(reporter)
        response = self.client.get(reverse('item_version'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['version'], item.updated_at.isoformat())

    def test_new_report_creates_a_notification_for_other_students(self):
        reporter = self.make_user('reporter')
        recipient = self.make_user('recipient')
        self.client.force_login(reporter)
        response = self.client.post(reverse('item_report'), {
            'title': 'Lost wallet',
            'description': 'Black wallet with a campus card.',
            'category': Item.Category.OTHERS,
            'status': Item.Status.LOST,
            'campus_location': 'Cafeteria',
        })
        self.assertEqual(response.status_code, 302)
        notification = Notification.objects.get(user=recipient)
        self.assertEqual(notification.item.title, 'Lost wallet')
        self.assertFalse(Notification.objects.filter(user=reporter).exists())

    def test_device_subscription_is_registered_and_can_be_removed(self):
        student = self.make_user('student')
        self.client.force_login(student)
        subscription = {
            'endpoint': 'https://push.example/device-1',
            'keys': {'p256dh': 'public-key', 'auth': 'auth-key'},
        }
        response = self.client.post(
            reverse('device_subscription'), subscription, content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(DeviceSubscription.objects.filter(user=student).exists())
        response = self.client.delete(
            reverse('device_subscription'), {'endpoint': subscription['endpoint']},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DeviceSubscription.objects.filter(user=student).exists())
