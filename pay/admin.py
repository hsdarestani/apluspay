from django.contrib import admin

from .models import AuditEvent, Business, LedgerEntry, Location, Membership, Plan, Subscription, Wallet

admin.site.site_header = "A+Pay Platform Administration"
admin.site.site_title = "A+Pay Admin"
admin.site.index_title = "Multi-Tenant Operations"


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "monthly_price", "max_locations", "max_staff", "is_active")


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "status", "currency", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("name", "slug", "legal_name", "contact_email")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "is_active")
    list_filter = ("business", "is_active")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "is_active")
    list_filter = ("role", "is_active", "business")
    search_fields = ("user__username", "user__email", "business__name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("business", "plan", "status", "trial_ends_at", "current_period_ends_at")
    list_filter = ("status", "plan")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("display_name", "business", "member_number", "balance", "status", "updated_at")
    list_filter = ("status", "business")
    search_fields = ("display_name", "phone", "email", "member_number", "qr_token")
    readonly_fields = ("id", "qr_token", "balance", "loyalty_points", "created_at", "updated_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "business", "wallet", "entry_type", "amount", "balance_after", "performed_by")
    list_filter = ("entry_type", "business", "created_at")
    search_fields = ("bill_number", "wallet__member_number", "order_reference", "idempotency_key")
    readonly_fields = [field.name for field in LedgerEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "business", "actor", "action", "object_type", "object_id")
    list_filter = ("business", "action", "created_at")
    readonly_fields = [field.name for field in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
