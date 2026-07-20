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
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["business", "slug"], name="unique_location_slug_per_business")]
        ordering = ["business__name", "name"]

    def __str__(self):
        return f"{self.business} · {self.name}"


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        STAFF = "STAFF", "Staff"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="apluspay_memberships")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "business"], name="unique_apluspay_membership")]
        ordering = ["business__name", "user__username"]

    def __str__(self):
        return f"{self.user} · {self.business} · {self.role}"


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


class Wallet(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Aktiv"
        BLOCKED = "BLOCKED", "Gesperrt"
        CLOSED = "CLOSED", "Geschlossen"

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
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    loyalty_points = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["business", "member_number"], name="unique_member_number_per_business"),
            models.UniqueConstraint(
                fields=["business", "owner"],
                condition=Q(owner__isnull=False),
                name="unique_customer_wallet_per_business",
            ),
        ]
        ordering = ["display_name"]

    def __str__(self):
        return f"{self.display_name} · {self.business}"


class LedgerEntry(models.Model):
    class Type(models.TextChoices):
        TOPUP = "TOPUP", "Aufladung"
        PURCHASE = "PURCHASE", "Einkauf"
        REFUND = "REFUND", "Erstattung"
        BONUS = "BONUS", "Bonus"
        ADJUSTMENT = "ADJUSTMENT", "Korrektur"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill_number = models.CharField(max_length=32, unique=True, default=generate_bill_number, editable=False, db_index=True)
    business = models.ForeignKey(Business, on_delete=models.PROTECT, related_name="ledger_entries")
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name="ledger_entries")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="ledger_entries")
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
            models.UniqueConstraint(
                fields=["business", "idempotency_key"],
                condition=~Q(idempotency_key=""),
                name="unique_apluspay_business_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "created_at"], name="pay_ledger_biz_date_idx"),
            models.Index(fields=["wallet", "created_at"], name="pay_ledger_wallet_date_idx"),
            models.Index(fields=["order_reference"], name="pay_ledger_order_ref_idx"),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount} · {self.wallet}"


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
