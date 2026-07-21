from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AppNotification, Business, LedgerEntry, Offer, PaymentRequest, PushDevice
from .serializers import BusinessSerializer, LedgerEntrySerializer, MeSerializer, MoneyActionSerializer, NotificationSerializer, OfferSerializer, PaymentRequestSerializer, PushDeviceSerializer, WalletSerializer
from .services import MANAGER_ROLES, STAFF_ROLES, client_ip, confirm_payment_request, create_payment_request, enroll_customer, post_wallet_entry, require_role


class MeView(APIView):
    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(MeSerializer(payload).data)


class VendorDirectoryView(APIView):
    def get(self, request):
        vendors = Business.objects.filter(is_discoverable=True, status__in=[Business.Status.TRIAL, Business.Status.ACTIVE]).select_related("vendor_app")
        return Response(BusinessSerializer(vendors, many=True).data)


class VendorJoinView(APIView):
    def post(self, request, business_slug):
        business = get_object_or_404(Business, slug=business_slug, is_discoverable=True)
        _, wallet = enroll_customer(user=request.user, business=business)
        return Response(WalletSerializer(wallet).data, status=status.HTTP_201_CREATED)


class VendorWalletView(APIView):
    def get(self, request, business_slug):
        wallet = get_object_or_404(request.user.apluspay_wallets.select_related("business"), business__slug=business_slug)
        return Response(WalletSerializer(wallet).data)


class VendorBootstrapView(APIView):
    def get(self, request, business_slug):
        business = get_object_or_404(Business.objects.select_related("vendor_app"), slug=business_slug, status__in=[Business.Status.TRIAL, Business.Status.ACTIVE])
        wallet = request.user.apluspay_wallets.filter(business=business).first()
        offers = business.offers.filter(is_active=True).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=timezone.now())).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=timezone.now()))
        pending = wallet.payment_requests.filter(status=PaymentRequest.Status.PENDING, expires_at__gte=timezone.now()) if wallet else PaymentRequest.objects.none()
        return Response({
            "vendor": BusinessSerializer(business).data,
            "wallet": WalletSerializer(wallet).data if wallet else None,
            "offers": OfferSerializer(offers, many=True).data,
            "pending_payments": PaymentRequestSerializer(pending, many=True).data,
            "locations": list(business.locations.filter(is_active=True).values("id", "name", "slug", "address", "google_review_url", "instagram_url", "tiktok_url")),
        })


class MyWalletsView(APIView):
    def get(self, request):
        wallets = request.user.apluspay_wallets.select_related("business", "business__vendor_app").all()
        return Response(WalletSerializer(wallets, many=True).data)


class BusinessWalletsView(APIView):
    def get(self, request, business_slug):
        business = get_object_or_404(Business, slug=business_slug)
        require_role(request.user, business, MANAGER_ROLES)
        wallets = business.wallets.select_related("business").all()[:500]
        return Response(WalletSerializer(wallets, many=True).data)


class BaseMoneyActionView(APIView):
    allowed_roles = STAFF_ROLES
    entry_type = LedgerEntry.Type.PURCHASE

    def post(self, request, business_slug):
        business = get_object_or_404(Business, slug=business_slug)
        require_role(request.user, business, self.allowed_roles)
        serializer = MoneyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        wallets = business.wallets.select_related("business")
        wallet = get_object_or_404(wallets, qr_token=data["wallet_token"]) if data.get("wallet_token") else get_object_or_404(wallets, member_number=data["member_number"])
        try:
            if self.entry_type == LedgerEntry.Type.PURCHASE:
                payment = create_payment_request(wallet=wallet, amount=data["amount"], tip_percentage=data.get("tip_percentage", 0), actor=request.user, description=data.get("description", ""), order_reference=data.get("order_reference", ""), ip_address=client_ip(request))
                return Response(PaymentRequestSerializer(payment).data, status=status.HTTP_201_CREATED)
            entry = post_wallet_entry(wallet=wallet, entry_type=self.entry_type, amount=data["amount"], actor=request.user, description=data.get("description", ""), order_reference=data.get("order_reference", ""), idempotency_key=data.get("idempotency_key", ""), ip_address=client_ip(request))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class StaffChargeView(BaseMoneyActionView):
    allowed_roles = STAFF_ROLES
    entry_type = LedgerEntry.Type.PURCHASE


class ManagerTopupView(BaseMoneyActionView):
    allowed_roles = MANAGER_ROLES
    entry_type = LedgerEntry.Type.TOPUP


class ManagerRefundView(BaseMoneyActionView):
    allowed_roles = MANAGER_ROLES
    entry_type = LedgerEntry.Type.REFUND


class CustomerPaymentConfirmView(APIView):
    def post(self, request, payment_id):
        payment = get_object_or_404(PaymentRequest.objects.select_related("wallet", "business"), pk=payment_id, wallet__owner=request.user)
        try:
            payment = confirm_payment_request(payment=payment, actor=request.user, ip_address=client_ip(request))
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PaymentRequestSerializer(payment).data)


class NotificationsView(APIView):
    def get(self, request):
        notifications = request.user.apluspay_notifications.select_related("business").all()[:100]
        return Response(NotificationSerializer(notifications, many=True).data)

    def post(self, request):
        notification = get_object_or_404(request.user.apluspay_notifications, pk=request.data.get("id"))
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class PushDeviceView(APIView):
    def post(self, request):
        serializer = PushDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, _ = PushDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={"user": request.user, "platform": serializer.validated_data["platform"], "is_active": serializer.validated_data.get("is_active", True)},
        )
        return Response(PushDeviceSerializer(device).data, status=status.HTTP_201_CREATED)
