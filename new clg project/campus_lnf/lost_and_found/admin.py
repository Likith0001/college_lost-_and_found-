from django.contrib import admin
from django.db import transaction
from django.utils.html import format_html
from .models import DeviceSubscription, Notification, UserProfile, Item, ClaimRequest

admin.site.site_header  = '🎓 Campus Lost & Found — Admin'
admin.site.site_title   = 'Campus L&F Admin'
admin.site.index_title  = 'Portal Administration'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'student_id', 'department', 'phone')
    search_fields = ('user__username', 'user__email', 'student_id', 'department')
    raw_id_fields = ('user',)


@admin.register(DeviceSubscription)
class DeviceSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'endpoint', 'updated_at')
    search_fields = ('user__username', 'user__email', 'endpoint')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'item', 'created_at', 'read_at')
    list_filter = ('created_at', 'read_at')
    search_fields = ('user__username', 'title', 'message')
    readonly_fields = ('created_at',)


class ClaimRequestInline(admin.TabularInline):
    """Show pending claims directly inside the Item detail page."""
    model        = ClaimRequest
    extra        = 0
    readonly_fields = ('requested_by', 'proof_description', 'date_requested', 'status')
    can_delete   = False


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display  = ('title', 'category', 'status', 'colored_status', 'campus_location',
                     'reported_by', 'submitted_at')
    list_filter   = ('status', 'category', 'submitted_at')
    search_fields = ('title', 'description', 'campus_location', 'reported_by__username')
    date_hierarchy = 'submitted_at'
    readonly_fields = ('submitted_at', 'reported_by', 'colored_status')
    list_editable = ('status',)
    inlines       = [ClaimRequestInline]

    fieldsets = (
        ('Item Details', {
            'fields': ('title', 'description', 'category', 'status', 'image')
        }),
        ('Location & Reporter', {
            'fields': ('campus_location', 'reported_by', 'submitted_at')
        }),
        ('Claim Info', {
            'fields': ('claimed_by',),
            'classes': ('collapse',),
        }),
    )

    @admin.display(description='Status')
    def colored_status(self, obj):
        colors = {
            'Lost':     '#dc3545',
            'Found':    '#198754',
            'Claimed':  '#ffc107',
            'Returned': '#6c757d',
        }
        color = colors.get(obj.status, '#0d6efd')
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>', color, obj.status
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.reported_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(ClaimRequest)
class ClaimRequestAdmin(admin.ModelAdmin):
    list_display  = ('item', 'requested_by', 'date_requested', 'colored_claim_status',
                     'approve_action')
    list_filter   = ('status', 'date_requested')
    search_fields = ('item__title', 'requested_by__username', 'proof_description')
    readonly_fields = ('item', 'requested_by', 'proof_description', 'date_requested')
    date_hierarchy  = 'date_requested'
    actions         = ['approve_claims', 'reject_claims']

    @admin.display(description='Status')
    def colored_claim_status(self, obj):
        colors = {'Pending': '#ffc107', 'Approved': '#198754', 'Rejected': '#dc3545'}
        color  = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span>', color, obj.status
        )

    @admin.display(description='Quick Action')
    def approve_action(self, obj):
        if obj.status == 'Pending':
            return format_html(
                '<a class="button" href="../{}/change/">Review</a>', obj.pk
            )
        return '—'

    @admin.action(description='✅ Approve selected claims')
    def approve_claims(self, request, queryset):
        approved = 0
        with transaction.atomic():
            for claim in queryset.filter(status='Pending').select_related('item', 'requested_by'):
                item = Item.objects.select_for_update().get(pk=claim.item_id)
                # Only one pending request can be approved for each found item.
                if item.status != Item.Status.FOUND:
                    continue
                claim.status = ClaimRequest.Status.APPROVED
                claim.save(update_fields=['status'])
                ClaimRequest.objects.filter(item=item, status=ClaimRequest.Status.PENDING).exclude(
                    pk=claim.pk
                ).update(status=ClaimRequest.Status.REJECTED)
                item.status = Item.Status.CLAIMED
                item.claimed_by = claim.requested_by
                item.save(update_fields=['status', 'claimed_by', 'updated_at'])
                approved += 1
        self.message_user(request, f'{approved} claim(s) approved.')

    @admin.action(description='❌ Reject selected claims')
    def reject_claims(self, request, queryset):
        updated = queryset.filter(status='Pending').update(status='Rejected')
        self.message_user(request, f'{updated} claim(s) rejected.')
