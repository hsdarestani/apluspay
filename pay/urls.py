from django.urls import path

from . import api, views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard_router, name="dashboard"),
    path("platform/", views.platform_dashboard, name="platform-dashboard"),
    path("platform/businesses/new/", views.platform_business_create, name="platform-business-create"),
    path("b/<slug:business_slug>/owner/", views.owner_dashboard, name="owner-dashboard"),
    path("b/<slug:business_slug>/staff/", views.staff_dashboard, name="staff-dashboard"),
    path("b/<slug:business_slug>/wallets/<uuid:wallet_id>/", views.owner_wallet_detail, name="owner-wallet-detail"),
    path("customer/", views.customer_dashboard, name="customer-dashboard"),
    path("customer/wallets/<uuid:wallet_id>/", views.customer_wallet_detail, name="customer-wallet-detail"),
    path("receipts/<str:bill_number>/", views.receipt, name="receipt"),
    path("sw.js", views.service_worker, name="service-worker"),
    path("api/v1/me/", api.MeView.as_view(), name="api-me"),
    path("api/v1/wallets/", api.MyWalletsView.as_view(), name="api-my-wallets"),
    path("api/v1/businesses/<slug:business_slug>/wallets/", api.BusinessWalletsView.as_view(), name="api-business-wallets"),
    path("api/v1/businesses/<slug:business_slug>/charge/", api.StaffChargeView.as_view(), name="api-charge"),
    path("api/v1/businesses/<slug:business_slug>/topup/", api.ManagerTopupView.as_view(), name="api-topup"),
    path("api/v1/businesses/<slug:business_slug>/refund/", api.ManagerRefundView.as_view(), name="api-refund"),
]
