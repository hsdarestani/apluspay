from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BusinessProvisionForm, CustomerCreateForm, MoneyActionForm, StaffCreateForm, WalletMoneyForm
from .models import Business, LedgerEntry, Plan, Wallet
from .services import (
    MANAGER_ROLES,
    STAFF_ROLES,
    client_ip,
    create_customer_wallet,
    create_staff_member,
    get_active_membership,
    is_platform_admin,
    post_wallet_entry,
    provision_business,
    require_role,
    set_wallet_status,
)


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "pay/landing.html")


@login_required
def dashboard_router(request):
    if is_platform_admin(request.user):
        return redirect("platform-dashboard")
    membership = get_active_membership(request.user)
    if membership:
        if membership.role in MANAGER_ROLES:
            return redirect("owner-dashboard", business_slug=membership.business.slug)
        return redirect("staff-dashboard", business_slug=membership.business.slug)
    if request.user.apluspay_wallets.exists():
        return redirect("customer-dashboard")
    raise PermissionDenied("Für dieses Konto wurde noch kein A+Pay-Zugang eingerichtet.")


@login_required
def platform_dashboard(request):
    if not is_platform_admin(request.user):
        raise PermissionDenied
    businesses = Business.objects.select_related("subscription__plan").annotate(
        wallet_count=Count("wallets", distinct=True),
        staff_count=Count("memberships", distinct=True),
    )
    stats = {
        "businesses": businesses.count(),
        "active_businesses": businesses.filter(status=Business.Status.ACTIVE).count(),
        "wallets": Wallet.objects.count(),
        "volume": LedgerEntry.objects.aggregate(total=Sum("amount"))["total"] or 0,
    }
    return render(request, "pay/platform_dashboard.html", {"businesses": businesses, "stats": stats})


@login_required
def platform_business_create(request):
    if not is_platform_admin(request.user):
        raise PermissionDenied
    if not Plan.objects.exists():
        Plan.objects.create(code="starter", name="Starter", monthly_price="49.00", max_locations=1, max_staff=5)
    form = BusinessProvisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        business, owner = provision_business(actor=request.user, **form.cleaned_data)
        messages.success(request, f"{business.name} und Owner {owner.username} wurden angelegt.")
        return redirect("platform-dashboard")
    return render(request, "pay/platform_business_form.html", {"form": form})


@login_required
def owner_dashboard(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    require_role(request.user, business, MANAGER_ROLES)

    customer_form = CustomerCreateForm(prefix="customer")
    staff_form = StaffCreateForm(prefix="staff")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_customer":
            customer_form = CustomerCreateForm(request.POST, prefix="customer")
            if customer_form.is_valid():
                wallet = create_customer_wallet(business=business, actor=request.user, **customer_form.cleaned_data)
                messages.success(request, f"Wallet {wallet.member_number} wurde erstellt.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "create_staff":
            staff_form = StaffCreateForm(request.POST, prefix="staff")
            if staff_form.is_valid():
                user = create_staff_member(business=business, actor=request.user, **staff_form.cleaned_data)
                messages.success(request, f"Teammitglied {user.username} wurde erstellt.")
                return redirect("owner-dashboard", business_slug=business.slug)

    wallets = business.wallets.select_related("owner").all()[:100]
    entries = business.ledger_entries.select_related("wallet", "performed_by")[:30]
    memberships = business.memberships.select_related("user").all()
    gross_credits = business.ledger_entries.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0
    gross_debits = business.ledger_entries.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0
    stats = {
        "wallets": business.wallets.count(),
        "staff": business.memberships.filter(is_active=True).count(),
        "outstanding": business.wallets.aggregate(total=Sum("balance"))["total"] or 0,
        "credits": gross_credits,
        "debits": abs(gross_debits),
    }
    return render(
        request,
        "pay/owner_dashboard.html",
        {
            "business": business,
            "wallets": wallets,
            "entries": entries,
            "memberships": memberships,
            "stats": stats,
            "customer_form": customer_form,
            "staff_form": staff_form,
        },
    )


@login_required
def staff_dashboard(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    require_role(request.user, business, STAFF_ROLES)
    form = MoneyActionForm(request.POST or None)
    wallet = None
    entry = None
    lookup = request.GET.get("member_number", "").strip()
    if lookup:
        wallet = business.wallets.filter(member_number=lookup).first()
    if request.method == "POST" and form.is_valid():
        wallet = get_object_or_404(business.wallets, member_number=form.cleaned_data["member_number"])
        try:
            entry = post_wallet_entry(
                wallet=wallet,
                entry_type=LedgerEntry.Type.PURCHASE,
                amount=form.cleaned_data["amount"],
                actor=request.user,
                description=form.cleaned_data["description"],
                order_reference=form.cleaned_data["order_reference"],
                ip_address=client_ip(request),
            )
            messages.success(request, f"Zahlung gebucht. Neuer Saldo: {entry.balance_after} {business.currency}")
            return redirect("receipt", bill_number=entry.bill_number)
        except ValidationError as exc:
            form.add_error(None, exc)
    recent_entries = business.ledger_entries.select_related("wallet")[:20]
    return render(
        request,
        "pay/staff_dashboard.html",
        {"business": business, "form": form, "wallet": wallet, "entry": entry, "recent_entries": recent_entries},
    )


@login_required
def owner_wallet_detail(request, business_slug, wallet_id):
    business = get_object_or_404(Business, slug=business_slug)
    require_role(request.user, business, MANAGER_ROLES)
    wallet = get_object_or_404(business.wallets.select_related("owner"), pk=wallet_id)
    money_form = WalletMoneyForm()
    if request.method == "POST":
        action = request.POST.get("submit_action")
        if action in {"block", "activate"}:
            status = Wallet.Status.BLOCKED if action == "block" else Wallet.Status.ACTIVE
            set_wallet_status(wallet=wallet, status=status, actor=request.user, ip_address=client_ip(request))
            messages.success(request, "Wallet-Status aktualisiert.")
            return redirect("owner-wallet-detail", business_slug=business.slug, wallet_id=wallet.pk)
        money_form = WalletMoneyForm(request.POST)
        if money_form.is_valid():
            data = money_form.cleaned_data
            try:
                entry = post_wallet_entry(
                    wallet=wallet,
                    entry_type=data["action"],
                    amount=data["amount"],
                    actor=request.user,
                    description=data["description"],
                    order_reference=data["order_reference"],
                    ip_address=client_ip(request),
                )
                messages.success(request, "Transaktion erfolgreich gebucht.")
                return redirect("receipt", bill_number=entry.bill_number)
            except ValidationError as exc:
                money_form.add_error(None, exc)
    return render(
        request,
        "pay/wallet_detail.html",
        {"business": business, "wallet": wallet, "entries": wallet.ledger_entries.all()[:100], "money_form": money_form, "management": True},
    )


@login_required
def customer_dashboard(request):
    wallets = request.user.apluspay_wallets.select_related("business").all()
    return render(request, "pay/customer_dashboard.html", {"wallets": wallets})


@login_required
def customer_wallet_detail(request, wallet_id):
    wallet = get_object_or_404(request.user.apluspay_wallets.select_related("business"), pk=wallet_id)
    return render(
        request,
        "pay/wallet_detail.html",
        {"business": wallet.business, "wallet": wallet, "entries": wallet.ledger_entries.all()[:100], "management": False},
    )


@login_required
def receipt(request, bill_number):
    entry = get_object_or_404(LedgerEntry.objects.select_related("business", "wallet", "performed_by"), bill_number=bill_number)
    allowed = is_platform_admin(request.user) or entry.wallet.owner_id == request.user.id
    if not allowed:
        membership = get_active_membership(request.user, entry.business)
        allowed = bool(membership)
    if not allowed:
        raise PermissionDenied
    return render(request, "pay/receipt.html", {"entry": entry})


def service_worker(_request):
    path = Path(__file__).resolve().parent / "static" / "pay" / "sw.js"
    response = HttpResponse(path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response
