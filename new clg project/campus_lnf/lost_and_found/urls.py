from django.conf import settings
from django.urls import path
from . import views

urlpatterns = [
    path('sw.js', views.service_worker_view, name='service_worker'),
    # Auth
    path('signup/',  views.signup_view,  name='signup'),
    path('login/',   views.login_view,   name='login'),
    path('logout/',  views.logout_view,  name='logout'),
    path('profile/', views.profile_view, name='profile'),

    # Dashboard (home)
    path('',         views.dashboard_view, name='dashboard'),
    path('api/items/version/', views.item_version_view, name='item_version'),
    path('api/devices/subscription/', views.device_subscription_view, name='device_subscription'),
    path('api/notifications/', views.notifications_view, name='notifications'),

    # Item CRUD
    path('report/',          views.item_report_view, name='item_report'),
    path('item/<str:pk>/',   views.item_detail_view, name='item_detail'),
    path('item/<str:pk>/edit/', views.item_edit_view, name='item_edit'),
    path('item/<str:pk>/delete/', views.item_delete_view, name='item_delete'),

    # My Items & Claims
    path('my-items/', views.my_items_view, name='my_items'),

    # Claim
    path('item/<str:pk>/claim/', views.claim_item_view, name='claim_item'),

    # Staff claim moderation
    path('staff/claims/', views.claim_review_list_view, name='claim_review_list'),
    path('staff/claims/<str:pk>/<str:decision>/', views.claim_decision_view,
         name='claim_decision'),
]

if settings.MONGODB_URI:
    urlpatterns.insert(0, path('media/<path:name>', views.gridfs_media_view, name='gridfs_media'))
