from pathlib import Path

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BusinessProvisionForm,
    BusinessSettingsForm,
    CustomerCreateForm,
    CustomerRegistrationForm,
    LocationForm,
    OfferForm,
    PaymentRequestForm,
    StaffCreateForm,
    VendorAppForm,
    WalletMoneyForm,
)
from .models import (
    AppNotification,
    Business,
    BusinessSettings,
    LedgerEntry,
    Offer,
    PaymentRequest,
    Plan,
    ReviewStatus,
    VendorApp,
    Wallet,
)
from .services import (
    MANAGER_ROLES,
    STAFF_ROLES,
    cancel_payment_request,
    client_ip,
    confirm_payment_request,
    create_customer_wallet,
    create_payment_request,
    create_staff_member,
    enroll_customer,
    get_active_membership,
    is_platform_admin,
    post_wallet_entry,
    provision_business,
    register_customer,
    require_role,
    set_wallet_status,
)


def landing(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    vendors = Business.objects.filter(
        is_discoverable=True,
        status__in=[Business.Status.TRIAL, Business.Status.ACTIVE],
    ).order_by("name")[:6]
    return render(request, "pay/landing.html", {"vendors": vendors})


def health(_request):
    return JsonResponse({"status": "ok", "service": "apluspay"})


def register_customer_view(request):
    if request.user.is_authenticated:
        return redirect("customer-dashboard")
    form = CustomerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = register_customer(form=form)
        login(request, user)
        messages.success(request, "Dein A+Pay-Konto ist bereit. Wähle jetzt deine Anbieter aus.")
        return redirect("customer-dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard_router(request):
    if is_platform_admin(request.user):
        return redirect("platform-dashboard")
    membership = get_active_membership(request.user)
    if membership:
        if membership.role in MANAGER_ROLES:
            return redirect("owner-dashboard", business_slug=membership.business.slug)
        return redirect("staff-dashboard", business_slug=membership.business.slug)
    return redirect("customer-dashboard")


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
        Plan.objects.create(code="starter", name="Start", monthly_price="49.00", max_locations=1, max_staff=5)
    form = BusinessProvisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        business, owner = provision_business(actor=request.user, **form.cleaned_data)
        messages.success(request, f"{business.name} und das Betreiberkonto {owner.username} wurden angelegt.")
        return redirect("platform-dashboard")
    return render(request, "pay/platform_business_form.html", {"form": form})


@login_required
def customer_dashboard(request):
    wallets = request.user.apluspay_wallets.select_related("business").filter(
        business__status__in=[Business.Status.TRIAL, Business.Status.ACTIVE]
    )
    joined_ids = list(wallets.values_list("business_id", flat=True))
    vendors = (
        Business.objects.filter(
            is_discoverable=True,
            status__in=[Business.Status.TRIAL, Business.Status.ACTIVE],
        )
        .exclude(pk__in=joined_ids)
        .select_related("vendor_app")[:30]
    )
    notifications = request.user.apluspay_notifications.select_related("business").all()[:8]
    totals = wallets.aggregate(balance=Sum("balance"), points=Sum("loyalty_points"))
    return render(
        request,
        "pay/customer_dashboard.html",
        {
            "wallets": wallets,
            "vendors": vendors,
            "notifications": notifications,
            "total_balance": totals["balance"] or 0,
            "total_points": totals["points"] or 0,
        },
    )


@login_required
def vendor_directory(request):
    query = request.GET.get("q", "").strip()
    vendors = Business.objects.filter(
        is_discoverable=True,
        status__in=[Business.Status.TRIAL, Business.Status.ACTIVE],
    ).select_related("vendor_app")
    if query:
        vendors = vendors.filter(
            Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
        )
    joined = set(request.user.apluspay_wallets.values_list("business_id", flat=True))
    return render(request, "pay/vendor_directory.html", {"vendors": vendors, "joined": joined, "query": query})


@login_required
def vendor_detail(request, business_slug):
    business = get_object_or_404(
        Business.objects.select_related("vendor_app"),
        slug=business_slug,
        is_discoverable=True,
    )
    wallet = request.user.apluspay_wallets.filter(business=business).first()
    offers = (
        business.offers.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=timezone.now()))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=timezone.now()))[:6]
    )
    return render(
        request,
        "pay/vendor_detail.html",
        {
            "business": business,
            "wallet": wallet,
            "offers": offers,
            "locations": business.locations.filter(is_active=True),
        },
    )


@login_required
def join_vendor(request, business_slug):
    if request.method != "POST":
        return redirect("vendor-detail", business_slug=business_slug)
    business = get_object_or_404(Business, slug=business_slug, is_discoverable=True)
    _, wallet = enroll_customer(user=request.user, business=business)
    messages.success(request, f"Du bist jetzt bei {business.name} registriert. Deine Karte ist aktiv.")
    return redirect("customer-vendor-dashboard", business_slug=business.slug)


@login_required
def customer_vendor_dashboard(request, business_slug):
    business = get_object_or_404(Business.objects.select_related("vendor_app"), slug=business_slug)
    wallet = get_object_or_404(
        request.user.apluspay_wallets.select_related("business", "location"),
        business=business,
    )
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=business)
    pending = wallet.payment_requests.filter(
        status=PaymentRequest.Status.PENDING,
        expires_at__gte=timezone.now(),
    )
    offers = (
        business.offers.filter(is_active=True)
        .filter(Q(target_tier=Offer.TargetTier.ALL) | Q(target_tier=wallet.tier))
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=timezone.now()))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=timezone.now()))[:10]
    )
    notifications = request.user.apluspay_notifications.filter(business=business)[:8]
    return render(
        request,
        "pay/customer_vendor_dashboard.html",
        {
            "business": business,
            "wallet": wallet,
            "settings": settings_obj,
            "pending_payments": pending,
            "offers": offers,
            "notifications": notifications,
            "entries": wallet.ledger_entries.all()[:15],
            "locations": business.locations.filter(is_active=True),
        },
    )


@login_required
def customer_payment_action(request, payment_id):
    payment = get_object_or_404(
        PaymentRequest.objects.select_related("wallet", "business"),
        pk=payment_id,
        wallet__owner=request.user,
    )
    if request.method == "POST":
        action = request.POST.get("action", "confirm")
        try:
            if action == "cancel":
                cancel_payment_request(payment=payment, actor=request.user)
                messages.info(request, "Zahlungsanfrage abgelehnt.")
            else:
                payment = confirm_payment_request(
                    payment=payment,
                    actor=request.user,
                    ip_address=client_ip(request),
                )
                messages.success(request, "Zahlung bestätigt.")
                return redirect("receipt", bill_number=payment.purchase_entry.bill_number)
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, str(exc))
    return redirect("customer-vendor-dashboard", business_slug=payment.business.slug)


@login_required
def mark_reviewed(request, business_slug, location_id):
    business = get_object_or_404(Business, slug=business_slug)
    wallet = get_object_or_404(request.user.apluspay_wallets, business=business)
    location = get_object_or_404(business.locations, pk=location_id)
    if request.method == "POST":
        status_obj, _ = ReviewStatus.objects.get_or_create(wallet=wallet, location=location)
        status_obj.completed_at = timezone.now()
        status_obj.save(update_fields=["completed_at"])
        messages.success(request, "Danke für deine Bewertung!")
    return redirect("customer-vendor-dashboard", business_slug=business.slug)


@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(request.user.apluspay_notifications, pk=notification_id)
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    return redirect(request.POST.get("next") or "customer-dashboard")


@login_required
def owner_dashboard(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    membership = require_role(request.user, business, MANAGER_ROLES)
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=business)
    vendor_app, _ = VendorApp.objects.get_or_create(business=business)
    customer_form = CustomerCreateForm(prefix="customer")
    staff_form = StaffCreateForm(prefix="staff")
    offer_form = OfferForm(prefix="offer")
    settings_form = BusinessSettingsForm(instance=settings_obj, prefix="settings")
    app_form = VendorAppForm(instance=vendor_app, prefix="app")
    location_form = LocationForm(prefix="location")
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_customer":
            customer_form = CustomerCreateForm(request.POST, prefix="customer")
            if customer_form.is_valid():
                wallet = create_customer_wallet(
                    business=business,
                    actor=request.user,
                    **customer_form.cleaned_data,
                )
                messages.success(request, f"Guthabenkonto {wallet.member_number} wurde erstellt.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "create_staff":
            staff_form = StaffCreateForm(request.POST, prefix="staff")
            if staff_form.is_valid():
                create_staff_member(business=business, actor=request.user, **staff_form.cleaned_data)
                messages.success(request, "Teammitglied wurde erstellt.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "create_offer":
            offer_form = OfferForm(request.POST, prefix="offer")
            if offer_form.is_valid():
                offer = offer_form.save(commit=False)
                offer.business = business
                offer.created_by = request.user
                offer.save()
                for wallet_owner in (
                    business.wallets.exclude(owner=None)
                    .values_list("owner_id", flat=True)
                    .distinct()
                ):
                    AppNotification.objects.create(
                        recipient_id=wallet_owner,
                        business=business,
                        kind=AppNotification.Kind.OFFER,
                        title=offer.title,
                        body=offer.body,
                        data={"offer_id": str(offer.pk)},
                    )
                messages.success(request, "Angebot veröffentlicht.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "update_settings":
            settings_form = BusinessSettingsForm(
                request.POST,
                instance=settings_obj,
                prefix="settings",
            )
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, "Guthaben- und Treueeinstellungen gespeichert.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "create_location":
            location_form = LocationForm(request.POST, prefix="location")
            if location_form.is_valid():
                location = location_form.save(commit=False)
                location.business = business
                location.save()
                messages.success(request, "Standort gespeichert.")
                return redirect("owner-dashboard", business_slug=business.slug)
        elif action == "update_app":
            app_form = VendorAppForm(request.POST, instance=vendor_app, prefix="app")
            if app_form.is_valid():
                app_form.save()
                messages.success(request, "Anbindung der Anbieter-App gespeichert.")
                return redirect("owner-dashboard", business_slug=business.slug)
    wallets = business.wallets.select_related("owner").all()[:100]
    entries = business.ledger_entries.select_related("wallet", "performed_by")[:30]
    memberships = business.memberships.select_related("user").all()
    payments = business.payment_requests.select_related("wallet", "created_by")[:20]
    stats = {
        "wallets": business.wallets.count(),
        "staff": business.memberships.filter(is_active=True).count(),
        "outstanding": business.wallets.aggregate(total=Sum("balance"))["total"] or 0,
        "credits": business.ledger_entries.filter(amount__gt=0).aggregate(total=Sum("amount"))["total"] or 0,
        "debits": abs(
            business.ledger_entries.filter(amount__lt=0).aggregate(total=Sum("amount"))["total"] or 0
        ),
    }
    return render(
        request,
        "pay/owner_dashboard.html",
        {
            "business": business,
            "wallets": wallets,
            "entries": entries,
            "memberships": memberships,
            "payments": payments,
            "offers": business.offers.all()[:8],
            "stats": stats,
            "customer_form": customer_form,
            "staff_form": staff_form,
            "offer_form": offer_form,
            "settings_form": settings_form,
            "app_form": app_form,
            "location_form": location_form,
            "locations": business.locations.all(),
            "membership": membership,
        },
    )


@login_required
def staff_dashboard(request, business_slug):
    business = get_object_or_404(Business, slug=business_slug)
    require_role(request.user, business, STAFF_ROLES)
    settings_obj, _ = BusinessSettings.objects.get_or_create(business=business)
    form = PaymentRequestForm(request.POST or None)
    wallet = None
    lookup = request.GET.get("member_number", "").strip()
    if lookup:
        wallet = business.wallets.filter(member_number=lookup).first()
    if request.method == "POST" and form.is_valid():
        wallet = get_object_or_404(
            business.wallets,
            member_number=form.cleaned_data["member_number"],
        )
        try:
            payment = create_payment_request(
                wallet=wallet,
                amount=form.cleaned_data["amount"],
                tip_percentage=form.cleaned_data["tip_percentage"],
                actor=request.user,
                location=wallet.location,
                description=form.cleaned_data["description"],
                order_reference=form.cleaned_data["order_reference"],
                ip_address=client_ip(request),
            )
            if payment.status == PaymentRequest.Status.CONFIRMED:
                messages.success(request, "Zahlung direkt gebucht.")
                return redirect("receipt", bill_number=payment.purchase_entry.bill_number)
            messages.success(request, "Zahlungsanfrage an den Kunden gesendet.")
            return redirect("staff-dashboard", business_slug=business.slug)
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "pay/staff_dashboard.html",
        {
            "business": business,
            "form": form,
            "wallet": wallet,
            "settings": settings_obj,
            "tip_options": settings_obj.tip_options(),
            "recent_entries": business.ledger_entries.select_related("wallet")[:20],
            "pending_payments": business.payment_requests.filter(status=PaymentRequest.Status.PENDING)[:12],
        },
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
            set_wallet_status(
                wallet=wallet,
                status=status,
                actor=request.user,
                ip_address=client_ip(request),
            )
            messages.success(request, "Status des Guthabenkontos aktualisiert.")
            return redirect(
                "owner-wallet-detail",
                business_slug=business.slug,
                wallet_id=wallet.pk,
            )
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
        {
            "business": business,
            "wallet": wallet,
            "entries": wallet.ledger_entries.all()[:100],
            "money_form": money_form,
            "management": True,
        },
    )


@login_required
def customer_wallet_detail(request, wallet_id):
    wallet = get_object_or_404(
        request.user.apluspay_wallets.select_related("business"),
        pk=wallet_id,
    )
    return redirect("customer-vendor-dashboard", business_slug=wallet.business.slug)


@login_required
def receipt(request, bill_number):
    entry = get_object_or_404(
        LedgerEntry.objects.select_related("business", "wallet", "performed_by"),
        bill_number=bill_number,
    )
    allowed = (
        is_platform_admin(request.user)
        or entry.wallet.owner_id == request.user.id
        or bool(get_active_membership(request.user, entry.business))
    )
    if not allowed:
        raise PermissionDenied
    return render(request, "pay/receipt.html", {"entry": entry})


def service_worker(_request):
    path = Path(__file__).resolve().parent / "static" / "pay" / "sw.js"
    response = HttpResponse(path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    return response
