from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import AuditEvent, Business, LedgerEntry, Location, Membership, Plan, Subscription, Wallet

User = get_user_model()
MANAGER_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER}
STAFF_ROLES = {Membership.Role.OWNER, Membership.Role.MANAGER, Membership.Role.STAFF}
CREDIT_TYPES = {LedgerEntry.Type.TOPUP, LedgerEntry.Type.REFUND, LedgerEntry.Type.BONUS}
DEBIT_TYPES = {LedgerEntry.Type.PURCHASE}


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def is_platform_admin(user):
    return bool(user and user.is_authenticated and (user.is_superuser or user.is_staff))


def get_active_membership(user, business=None):
    memberships = Membership.objects.select_related("business").filter(
        user=user,
        is_active=True,
        business__status__in=[Business.Status.TRIAL, Business.Status.ACTIVE],
    )
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
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Ungültiger Betrag.") from exc
    if amount <= 0:
        raise ValidationError("Der Betrag muss größer als 0 sein.")
    return amount


@transaction.atomic
def provision_business(*, business_name, slug, owner_username, owner_email, owner_password, plan, location_name="Hauptstandort", actor=None):
    owner = User.objects.create_user(username=owner_username, email=owner_email, password=owner_password)
    business = Business.objects.create(name=business_name, slug=slug, contact_email=owner_email)
    Membership.objects.create(user=owner, business=business, role=Membership.Role.OWNER)
    Location.objects.create(business=business, name=location_name, slug="main")
    Subscription.objects.create(
        business=business,
        plan=plan,
        status=Subscription.Status.TRIAL,
        trial_ends_at=timezone.now() + timedelta(days=14),
    )
    AuditEvent.objects.create(
        actor=actor,
        business=business,
        action="platform.business_created",
        object_type="business",
        object_id=str(business.pk),
        details={"owner_username": owner.username, "plan": plan.code},
    )
    return business, owner


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
    AuditEvent.objects.create(
        actor=actor,
        business=business,
        action="membership.created",
        object_type="user",
        object_id=str(user.pk),
        details={"username": username, "role": role},
    )
    return user


@transaction.atomic
def create_customer_wallet(*, business, username, email, phone, password, display_name, initial_balance, actor):
    user = User.objects.create_user(username=username, email=email, password=password)
    wallet = Wallet.objects.create(
        owner=user,
        business=business,
        location=business.locations.filter(is_active=True).first(),
        display_name=display_name,
        email=email,
        phone=phone,
    )
    AuditEvent.objects.create(
        actor=actor,
        business=business,
        action="wallet.created",
        object_type="wallet",
        object_id=str(wallet.pk),
        details={"username": username, "member_number": wallet.member_number},
    )
    if initial_balance and Decimal(str(initial_balance)) > 0:
        post_wallet_entry(
            wallet=wallet,
            entry_type=LedgerEntry.Type.TOPUP,
            amount=initial_balance,
            actor=actor,
            description="Startguthaben",
        )
    return wallet


@transaction.atomic
def post_wallet_entry(*, wallet, entry_type, amount, actor, location=None, description="", order_reference="", idempotency_key="", ip_address=None):
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
    if entry_type == LedgerEntry.Type.PURCHASE:
        locked_wallet.loyalty_points += max(1, int(amount))
        update_fields = ["balance", "loyalty_points", "updated_at"]
    else:
        update_fields = ["balance", "updated_at"]
    locked_wallet.save(update_fields=update_fields)
    entry = LedgerEntry.objects.create(
        business=locked_wallet.business,
        location=location or locked_wallet.location,
        wallet=locked_wallet,
        entry_type=entry_type,
        amount=signed_amount,
        balance_before=before,
        balance_after=after,
        description=description.strip(),
        order_reference=order_reference.strip(),
        idempotency_key=idempotency_key.strip(),
        performed_by=actor,
    )
    AuditEvent.objects.create(
        actor=actor,
        business=locked_wallet.business,
        action=f"wallet.{entry_type.lower()}",
        object_type="wallet",
        object_id=str(locked_wallet.pk),
        ip_address=ip_address,
        details={
            "ledger_entry_id": str(entry.pk),
            "bill_number": entry.bill_number,
            "member_number": locked_wallet.member_number,
            "amount": str(signed_amount),
            "balance_before": str(before),
            "balance_after": str(after),
            "order_reference": order_reference,
        },
    )
    return entry


@transaction.atomic
def set_wallet_status(*, wallet, status, actor, ip_address=None):
    if status not in Wallet.Status.values:
        raise ValidationError("Ungültiger Wallet-Status.")
    locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    old_status = locked_wallet.status
    locked_wallet.status = status
    locked_wallet.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(
        actor=actor,
        business=locked_wallet.business,
        action="wallet.status_changed",
        object_type="wallet",
        object_id=str(locked_wallet.pk),
        ip_address=ip_address,
        details={"from": old_status, "to": status},
    )
    return locked_wallet
