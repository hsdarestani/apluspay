from django.contrib import admin

from .models import (
    AppNotification, AuditEvent, Business, BusinessSettings, CustomerVendorEnrollment,
    LedgerEntry, Location, MemberProfile, Membership, Offer, PaymentRequest, Plan,
    PushDevice, ReviewStatus, Subscription, VendorApp, Wallet,
)

admin.site.site_header = "A+Pay-Verwaltung"
admin.site.site_title = "A+Pay-Verwaltung"
admin.site.index_title = "Zentrale Plattformverwaltung"


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "status", "is_discoverable", "created_at")
    list_filter = ("status", "is_discoverable", "category")
    search_fields = ("name", "slug", "legal_name", "contact_email")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("display_name", "business", "member_number", "tier", "balance", "status")
    list_filter = ("business", "status", "tier")
    search_fields = ("display_name", "member_number", "email", "phone")


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("wallet", "business", "base_amount", "tip_amount", "status", "created_at")
    list_filter = ("business", "status")


admin.site.register(Plan)
admin.site.register(Location)
admin.site.register(BusinessSettings)
admin.site.register(VendorApp)
admin.site.register(Membership)
admin.site.register(MemberProfile)
admin.site.register(Subscription)
admin.site.register(CustomerVendorEnrollment)
admin.site.register(LedgerEntry)
admin.site.register(Offer)
admin.site.register(ReviewStatus)
admin.site.register(AppNotification)
admin.site.register(PushDevice)
admin.site.register(AuditEvent)
