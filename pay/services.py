from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AppNotification, AuditEvent, Business, BusinessSettings, CustomerVendorEnrollment,
    LedgerEntry, Location, MemberProfile, Membership, PaymentRequest, Plan, Subscription,
    VendorApp, Wallet,
)

User = get_user_model()
MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
STAFF_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF}
CREDIT_TYPES = {LedgerEntry.Type.TOPUP, LedgerEntry.Type.REFUND, LedgerEntry.Type.BONUS}
DEBIT_TYPES = {LedgerEntry.Type.PURCHASE, LedgerEntry.Type.TIP}


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def is_platform_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def get_active_membership(user, business=None):
    memberships = Membership.objects.select_related("business").filter(user=user, is_active=True, business__status__in=[Business.Status.TRIAL, Business.Status.ACTIVE])
    if business is not None:
        memberships = memberships.filter(business=business)
    return memberships.first()


def require_role(user, business, allowed_roles):
    if is_platform_admin(user):
        return None
    membership = get_active_membership(user, business)
    if not membership or membership.role not in allowed_roles:
        raise PermissionDenied("Keine Berechtigung für diese Aktion.")
    return membership


def normalize_amount(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Ungültiger Betrag.") from exc
    if amount <= 0:
        raise ValidationError("Der Betrag muss größer als 0 sein.")
    return amount


def profile_display_name(user):
    profile = getattr(user, "apluspay_profile", None)
    return (getattr(profile, "display_name", "") or user.get_full_name() or user.username).strip()


@transaction.atomic
def provision_business(*, business_name, slug, owner_username, owner_email, owner_password, plan, location_name="Hauptstandort", category="Hospitality", actor=None):
    owner = User.objects.create_user(username=owner_username, email=owner_email, password=owner_password)
    business = Business.objects.create(name=business_name, slug=slug, contact_email=owner_email, category=category)
    Membership.objects.create(user=owner, business=business, role=Membership.Role.OWNER, can_manage_content=True)
    Location.objects.create(business=business, name=location_name, slug="main")
    BusinessSettings.objects.create(business=business)
    VendorApp.objects.create(business=business)
    Subscription.objects.create(business=business, plan=plan, status=Subscription.Status.TRIAL, trial_ends_at=timezone.now() + timedelta(days=14))
    AuditEvent.objects.create(actor=actor, business=business, action="platform.business_created", object_type="business", object_id=str(business.pk), details={"owner_username": owner.username, "plan": plan.code})
    return business, owner


@transaction.atomic
def register_customer(*, form):
    user = form.save(commit=False)
    user.email = form.cleaned_data["email"]
    user.first_name = form.cleaned_data["first_name"]
    user.last_name = form.cleaned_data["last_name"]
    user.save()
    MemberProfile.objects.create(user=user, display_name=user.get_full_name(), phone=form.cleaned_data.get("phone", ""), marketing_opt_in=form.cleaned_data.get("marketing_opt_in", False))
    return user


@transaction.atomic
def enroll_customer(*, user, business, source=CustomerVendorEnrollment.Source.APLUSPAY, external_customer_id=""):
    if not business.is_active:
        raise ValidationError("Dieser Anbieter ist derzeit nicht verfügbar.")
    enrollment, _ = CustomerVendorEnrollment.objects.update_or_create(
        user=user, business=business,
        defaults={"is_active": True, "source": source, "external_customer_id": external_customer_id},
    )
    wallet, created = Wallet.objects.get_or_create(
        owner=user, business=business,
        defaults={
            "location": business.locations.filter(is_active=True).first(),
            "display_name": profile_display_name(user),
            "email": user.email,
            "phone": getattr(getattr(user, "apluspay_profile", None), "phone", ""),
        },
    )
    if created:
        AppNotification.objects.create(recipient=user, business=business, kind=AppNotification.Kind.SYSTEM, title=f"Willkommen bei {business.name}", body="Deine digitale Karte ist bereit. Du kannst sie sofort in A+Pay verwenden.")
        AuditEvent.objects.create(actor=user, business=business, action="customer.enrolled", object_type="wallet", object_id=str(wallet.pk), details={"source": source})
    return enrollment, wallet


@transaction.atomic
def create_staff_member(*, business, username, email, password, role, actor):
    if role not in {Membership.Role.MANAGER, Membership.Role.STAFF}:
        raise ValidationError("Diese Rolle kann hier nicht vergeben werden.")
    if not is_platform_admin(actor):
        actor_membership = get_active_membership(actor, business)
        if not actor_membership or actor_membership.role not in MANAGER_ROLES:
            raise PermissionDenied("Keine Berechtigung für diese Aktion.")
        if actor_membership.role == Membership.Role.MANAGER and role != Membership.Role.STAFF:
            raise PermissionDenied("Manager dürfen nur Staff-Zugänge anlegen.")
    user = User.objects.create_user(username=username, email=email, password=password)
    Membership.objects.create(user=user, business=business, role=role)
    AuditEvent.objects.create(actor=actor, business=business, action="membership.created", object_type="user", object_id=str(user.pk), details={"username": username, "role": role})
    return user


@transaction.atomic
def create_customer_wallet(*, business, username, email, phone, password, display_name, initial_balance, actor):
    user = User.objects.create_user(username=username, email=email, password=password, first_name=display_name)
    MemberProfile.objects.create(user=user, display_name=display_name, phone=phone)
    _, wallet = enroll_customer(user=user, business=business, source=CustomerVendorEnrollment.Source.STAFF)
    if initial_balance and Decimal(str(initial_balance)) > 0:
        post_wallet_entry(wallet=wallet, entry_type=LedgerEntry.Type.TOPUP, amount=initial_balance, actor=actor, description="Startguthaben")
    return wallet


def update_wallet_tier(wallet):
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=wallet.business)
    if wallet.monthly_topup_total >= settings_obj.platinum_threshold:
        tier = Wallet.Tier.PLATINUM
    elif wallet.monthly_topup_total >= settings_obj.gold_threshold:
        tier = Wallet.Tier.GOLD
    else:
        tier = Wallet.Tier.SILVER
    if wallet.tier != tier:
        wallet.tier = tier
        wallet.save(update_fields=["tier", "updated_at"])
    return tier


@transaction.atomic
def post_wallet_entry(*, wallet, entry_type, amount, actor, location=None, payment_request=None, description="", order_reference="", idempotency_key="", ip_address=None):
    amount = normalize_amount(amount)
    locked_wallet = Wallet.objects.select_for_update().select_related("business").get(pk=wallet.pk)
    if locked_wallet.status != Wallet.Status.ACTIVE:
        raise ValidationError("Dieses Wallet ist nicht aktiv.")
    if entry_type in CREDIT_TYPES:
        signed_amount = amount
    elif entry_type in DEBIT_TYPES:
        signed_amount = -amount
    elif entry_type == LedgerEntry.Type.ADJUSTMENT:
        signed_amount = amount
    else:
        raise ValidationError("Unbekannter Transaktionstyp.")
    before = locked_wallet.balance
    after = before + signed_amount
    if after < 0:
        raise ValidationError("Nicht genügend Guthaben.")
    locked_wallet.balance = after
    update_fields = ["balance", "updated_at"]
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=locked_wallet.business)
    if entry_type == LedgerEntry.Type.PURCHASE and settings_obj.loyalty_enabled:
        locked_wallet.loyalty_points += max(1, int(amount))
        update_fields.append("loyalty_points")
    if entry_type == LedgerEntry.Type.TOPUP:
        locked_wallet.monthly_topup_total += amount
        update_fields.append("monthly_topup_total")
    locked_wallet.save(update_fields=update_fields)
    if entry_type == LedgerEntry.Type.TOPUP:
        update_wallet_tier(locked_wallet)
    entry = LedgerEntry.objects.create(
        business=locked_wallet.business, location=location or locked_wallet.location, wallet=locked_wallet,
        payment_request=payment_request, entry_type=entry_type, amount=signed_amount,
        balance_before=before, balance_after=after, description=description.strip(),
        order_reference=order_reference.strip(), idempotency_key=idempotency_key.strip(), performed_by=actor,
    )
    AuditEvent.objects.create(actor=actor, business=locked_wallet.business, action=f"wallet.{entry_type.lower()}", object_type="wallet", object_id=str(locked_wallet.pk), ip_address=ip_address, details={"ledger_entry_id": str(entry.pk), "bill_number": entry.bill_number, "member_number": locked_wallet.member_number, "amount": str(signed_amount), "balance_before": str(before), "balance_after": str(after), "order_reference": order_reference})
    return entry


@transaction.atomic
def create_payment_request(*, wallet, amount, tip_percentage, actor, location=None, description="", order_reference="", ip_address=None):
    base_amount = normalize_amount(amount)
    tip_percentage = Decimal(str(tip_percentage or 0)).quantize(Decimal("0.01"))
    tip_amount = (base_amount * tip_percentage / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=wallet.business)
    requires_confirmation = bool(settings_obj.require_customer_confirmation and wallet.owner_id)
    payment = PaymentRequest.objects.create(
        business=wallet.business, location=location or wallet.location, wallet=wallet, created_by=actor,
        base_amount=base_amount, tip_percentage=tip_percentage, tip_amount=tip_amount,
        description=description.strip(), order_reference=order_reference.strip(),
        customer_confirmation_required=requires_confirmation, expires_at=timezone.now() + timedelta(minutes=10),
    )
    if wallet.owner_id:
        AppNotification.objects.create(recipient=wallet.owner, business=wallet.business, location=payment.location, kind=AppNotification.Kind.PAYMENT, title=f"Zahlung bei {wallet.business.name}", body=f"Bitte bestätige {payment.total_amount} {wallet.business.currency}.", data={"payment_id": str(payment.pk)})
    if not requires_confirmation:
        confirm_payment_request(payment=payment, actor=actor, ip_address=ip_address, staff_override=True)
    return payment


@transaction.atomic
def confirm_payment_request(*, payment, actor, ip_address=None, staff_override=False):
    payment = PaymentRequest.objects.select_for_update().select_related("wallet", "business").get(pk=payment.pk)
    if payment.status != PaymentRequest.Status.PENDING:
        raise ValidationError("Diese Zahlung wurde bereits bearbeitet.")
    if payment.expires_at and payment.expires_at < timezone.now():
        payment.status = PaymentRequest.Status.EXPIRED
        payment.save(update_fields=["status"])
        raise ValidationError("Diese Zahlungsanfrage ist abgelaufen.")
    if not staff_override and payment.wallet.owner_id != actor.id and not is_platform_admin(actor):
        raise PermissionDenied("Diese Zahlung gehört nicht zu deinem Konto.")
    purchase = post_wallet_entry(wallet=payment.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount=payment.base_amount, actor=payment.created_by, location=payment.location, payment_request=payment, description=payment.description or "A+Pay Zahlung", order_reference=payment.order_reference, ip_address=ip_address)
    tip_entry = None
    if payment.tip_amount > 0:
        tip_entry = post_wallet_entry(wallet=payment.wallet, entry_type=LedgerEntry.Type.TIP, amount=payment.tip_amount, actor=payment.created_by, location=payment.location, payment_request=payment, description="Trinkgeld", order_reference=payment.order_reference, ip_address=ip_address)
    payment.purchase_entry = purchase
    payment.tip_entry = tip_entry
    payment.status = PaymentRequest.Status.CONFIRMED
    payment.confirmed_at = timezone.now()
    payment.save(update_fields=["purchase_entry", "tip_entry", "status", "confirmed_at"])
    if payment.wallet.owner_id:
        AppNotification.objects.create(recipient=payment.wallet.owner, business=payment.business, location=payment.location, kind=AppNotification.Kind.PAYMENT, title="Zahlung erfolgreich", body=f"{payment.total_amount} {payment.business.currency} wurden bezahlt.", data={"bill_number": purchase.bill_number})
    return payment


@transaction.atomic
def cancel_payment_request(*, payment, actor):
    payment = PaymentRequest.objects.select_for_update().get(pk=payment.pk)
    if payment.wallet.owner_id != actor.id and not is_platform_admin(actor):
        raise PermissionDenied
    if payment.status == PaymentRequest.Status.PENDING:
        payment.status = PaymentRequest.Status.CANCELLED
        payment.save(update_fields=["status"])
    return payment


@transaction.atomic
def set_wallet_status(*, wallet, status, actor, ip_address=None):
    if status not in Wallet.Status.values:
        raise ValidationError("Ungültiger Wallet-Status.")
    locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    old_status = locked_wallet.status
    locked_wallet.status = status
    locked_wallet.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, business=locked_wallet.business, action="wallet.status_changed", object_type="wallet", object_id=str(locked_wallet.pk), ip_address=ip_address, details={"from": old_status, "to": status})
    return locked_wallet
