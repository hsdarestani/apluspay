import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def generate_member_number():
    return str(secrets.randbelow(90_000_000) + 10_000_000)


def generate_bill_number():
    return f"AP-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"


class Plan(models.Model):
    code = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    monthly_price = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("0.00"))
    max_locations = models.PositiveIntegerField(default=1)
    max_staff = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["monthly_price", "name"]

    def __str__(self):
        return self.name


class Business(models.Model):
    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Testphase"
        ACTIVE = "ACTIVE", "Aktiv"
        SUSPENDED = "SUSPENDED", "Gesperrt"

    name = models.CharField(max_length=140)
    slug = models.SlugField(unique=True)
    legal_name = models.CharField(max_length=180, blank=True)
    vat_id = models.CharField(max_length=40, blank=True)
    contact_email = models.EmailField(blank=True)
    currency = models.CharField(max_length=3, default="EUR")
    primary_color = models.CharField(max_length=7, default="#F5B800")
    category = models.CharField(max_length=80, blank=True, default="Hospitality")
    description = models.TextField(blank=True)
    logo_url = models.URLField(blank=True)
    cover_url = models.URLField(blank=True)
    is_discoverable = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    @property
    def is_active(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE}

    def __str__(self):
        return self.name


class Location(models.Model):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="locations")
    name = models.CharField(max_length=120)
    slug = models.SlugField()
    address = models.CharField(max_length=255, blank=True)
    google_review_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["business", "slug"], name="unique_location_slug_per_business")]
        ordering = ["position", "business__name", "name"]

    def __str__(self):
        return f"{self.business} · {self.name}"


class BusinessSettings(models.Model):
    class TipAllocation(models.TextChoices):
        TEAM = "TEAM", "Team"
        EMPLOYEE = "EMPLOYEE", "Einzelne Person"

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="app_settings")
    require_customer_confirmation = models.BooleanField(default=True)
    tip_option_1 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tip_option_2 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("5.00"))
    tip_option_3 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    tip_option_4 = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("15.00"))
    tip_allocation = models.CharField(max_length=12, choices=TipAllocation.choices, default=TipAllocation.TEAM)
    gold_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("500.00"))
    platinum_threshold = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("700.00"))
    birthday_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    loyalty_enabled = models.BooleanField(default=True)
    reviews_enabled = models.BooleanField(default=True)
    offers_enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def tip_options(self):
        return [self.tip_option_1, self.tip_option_2, self.tip_option_3, self.tip_option_4]

    def __str__(self):
        return f"Settings · {self.business}"


class VendorApp(models.Model):
    class Mode(models.TextChoices):
        NONE = "NONE", "Keine eigene App"
        LINK = "LINK", "Externer Link / Deep Link"
        SHARED_API = "SHARED_API", "Gemeinsame A+Pay API"
        SSO = "SSO", "Shared Identity / SSO"

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="vendor_app")
    mode = models.CharField(max_length=16, choices=Mode.choices, default=Mode.NONE)
    app_name = models.CharField(max_length=120, blank=True)
    icon_url = models.URLField(blank=True)
    web_url = models.URLField(blank=True)
    ios_url = models.URLField(blank=True)
    android_url = models.URLField(blank=True)
    deep_link = models.CharField(max_length=255, blank=True)
    public_client_id = models.CharField(max_length=80, blank=True)
    show_in_apluspay = models.BooleanField(default=True)
    shared_identity_enabled = models.BooleanField(default=False)
    external_registration_enabled = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_enabled(self):
        return self.mode != self.Mode.NONE and self.show_in_apluspay

    def __str__(self):
        return self.app_name or f"App · {self.business}"


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        STAFF = "STAFF", "Staff"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apluspay_memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    can_manage_content = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "business"], name="unique_apluspay_membership")]
        ordering = ["business__name", "user__username"]

    def __str__(self):
        return f"{self.user} · {self.business} · {self.role}"


class MemberProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apluspay_profile")
    display_name = models.CharField(max_length=140, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    age_confirmed = models.BooleanField(default=False)
    marketing_opt_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.display_name or self.user.get_full_name() or self.user.username


class Subscription(models.Model):
    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Testphase"
        ACTIVE = "ACTIVE", "Aktiv"
        PAST_DUE = "PAST_DUE", "Überfällig"
        CANCELLED = "CANCELLED", "Gekündigt"

    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.TRIAL)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business} · {self.plan}"


class CustomerVendorEnrollment(models.Model):
    class Source(models.TextChoices):
        APLUSPAY = "APLUSPAY", "A+Pay"
        DEDICATED_APP = "DEDICATED_APP", "Vendor App"
        API = "API", "API"
        STAFF = "STAFF", "Staff"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor_enrollments")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="customer_enrollments")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.APLUSPAY)
    external_customer_id = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "business"], name="unique_customer_vendor_enrollment")]
        ordering = ["-joined_at"]

    def __str__(self):
        return f"{self.user} · {self.business}"


class Wallet(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Aktiv"
        BLOCKED = "BLOCKED", "Gesperrt"
        CLOSED = "CLOSED", "Geschlossen"

    class Tier(models.TextChoices):
        SILVER = "SILVER", "Silber"
        GOLD = "GOLD", "Gold"
        PLATINUM = "PLATINUM", "Platinum"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="wallets")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="wallets")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="apluspay_wallets")
    member_number = models.CharField(max_length=8, default=generate_member_number, db_index=True, editable=False)
    display_name = models.CharField(max_length=140)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    tier = models.CharField(max_length=12, choices=Tier.choices, default=Tier.SILVER)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    monthly_topup_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    loyalty_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "member_number"], name="unique_member_number_per_business"),
            models.UniqueConstraint(fields=["business", "owner"], condition=Q(owner__isnull=False), name="unique_customer_wallet_per_business"),
        ]
        ordering = ["display_name"]

    def __str__(self):
        return f"{self.display_name} · {self.business}"


class PaymentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Wartet auf Bestätigung"
        CONFIRMED = "CONFIRMED", "Bestätigt"
        CANCELLED = "CANCELLED", "Storniert"
        EXPIRED = "EXPIRED", "Abgelaufen"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="payment_requests")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="payment_requests")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="payment_requests")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="apluspay_created_payment_requests")
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    tip_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    tip_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    description = models.CharField(max_length=255, blank=True)
    order_reference = models.CharField(max_length=100, blank=True)
    customer_confirmation_required = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    purchase_entry = models.OneToOneField("LedgerEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_payment_request")
    tip_entry = models.OneToOneField("LedgerEntry", on_delete=models.SET_NULL, null=True, blank=True, related_name="tip_payment_request")
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "status", "created_at"], name="pay_req_wallet_status_idx"),
            models.Index(fields=["business", "location", "created_at"], name="pay_req_biz_loc_idx"),
        ]

    @property
    def total_amount(self):
        return self.base_amount + self.tip_amount

    def __str__(self):
        return f"{self.wallet} · {self.total_amount} · {self.status}"


class LedgerEntry(models.Model):
    class Type(models.TextChoices):
        TOPUP = "TOPUP", "Aufladung"
        PURCHASE = "PURCHASE", "Einkauf"
        TIP = "TIP", "Trinkgeld"
        REFUND = "REFUND", "Erstattung"
        BONUS = "BONUS", "Bonus"
        ADJUSTMENT = "ADJUSTMENT", "Korrektur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill_number = models.CharField(max_length=32, unique=True, default=generate_bill_number, editable=False, db_index=True)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="ledger_entries")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="ledger_entries")
    payment_request = models.ForeignKey(PaymentRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries")
    entry_type = models.CharField(max_length=16, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    order_reference = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="apluspay_ledger_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(amount=0), name="apluspay_ledger_amount_not_zero"),
            models.UniqueConstraint(fields=["business", "idempotency_key"], condition=~Q(idempotency_key=""), name="unique_apluspay_business_idempotency_key"),
        ]
        indexes = [
            models.Index(fields=["business", "created_at"], name="pay_ledger_biz_date_idx"),
            models.Index(fields=["wallet", "created_at"], name="pay_ledger_wallet_date_idx"),
            models.Index(fields=["order_reference"], name="pay_ledger_order_ref_idx"),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount} · {self.wallet}"


class Offer(models.Model):
    class TargetTier(models.TextChoices):
        ALL = "ALL", "Alle"
        SILVER = "SILVER", "Silber"
        GOLD = "GOLD", "Gold"
        PLATINUM = "PLATINUM", "Platinum"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="offers")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, null=True, blank=True, related_name="offers")
    title = models.CharField(max_length=180)
    body = models.TextField()
    image_url = models.URLField(blank=True)
    target_tier = models.CharField(max_length=12, choices=TargetTier.choices, default=TargetTier.ALL)
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="apluspay_created_offers")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class ReviewStatus(models.Model):
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="review_statuses")
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name="review_statuses")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["wallet", "location"], name="unique_wallet_location_review")]

    @property
    def is_completed(self):
        return self.completed_at is not None


class AppNotification(models.Model):
    class Kind(models.TextChoices):
        PAYMENT = "PAYMENT", "Zahlung"
        OFFER = "OFFER", "Angebot"
        BIRTHDAY = "BIRTHDAY", "Geburtstag"
        SYSTEM = "SYSTEM", "System"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apluspay_notifications")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="notifications")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    title = models.CharField(max_length=160)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "created_at"], name="pay_notif_rec_read_idx")]


class PushDevice(models.Model):
    class Platform(models.TextChoices):
        IOS = "IOS", "iOS"
        ANDROID = "ANDROID", "Android"
        WEB = "WEB", "Web"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apluspay_push_devices")
    platform = models.CharField(max_length=12, choices=Platform.choices)
    token = models.CharField(max_length=512, unique=True)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} · {self.platform}"


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="apluspay_audit_events")
    business = models.ForeignKey(Business, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events")
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80)
    object_id = models.CharField(max_length=80)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "created_at"], name="pay_audit_biz_date_idx")]

    def __str__(self):
        return f"{self.action} · {self.object_type}:{self.object_id}"
