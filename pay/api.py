from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Business, LedgerEntry, Wallet
from .serializers import LedgerEntrySerializer, MeSerializer, MoneyActionSerializer, WalletSerializer
from .services import MANAGER_ROLES, STAFF_ROLES, client_ip, post_wallet_entry, require_role


class MeView(APIView):
    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(MeSerializer(payload).data)


class MyWalletsView(APIView):
    def get(self, request):
        wallets = request.user.apluspay_wallets.select_related("business").all()
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
        if data.get("wallet_token"):
            wallet = get_object_or_404(wallets, qr_token=data["wallet_token"])
        else:
            wallet = get_object_or_404(wallets, member_number=data["member_number"])
        try:
            entry = post_wallet_entry(
                wallet=wallet,
                entry_type=self.entry_type,
                amount=data["amount"],
                actor=request.user,
                description=data.get("description", ""),
                order_reference=data.get("order_reference", ""),
                idempotency_key=data.get("idempotency_key", ""),
                ip_address=client_ip(request),
            )
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
