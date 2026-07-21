from decimal import Decimal

from rest_framework import serializers

from .models import Business, LedgerEntry, Membership, Wallet


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = ["id", "name", "slug", "currency", "primary_color", "status"]


class WalletSerializer(serializers.ModelSerializer):
    business = BusinessSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id",
            "business",
            "member_number",
            "display_name",
            "status",
            "balance",
            "loyalty_points",
            "qr_token",
            "updated_at",
        ]


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "bill_number",
            "entry_type",
            "amount",
            "balance_before",
            "balance_after",
            "description",
            "order_reference",
            "created_at",
        ]


class MoneyActionSerializer(serializers.Serializer):
    wallet_token = serializers.UUIDField(required=False)
    member_number = serializers.CharField(max_length=8, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)
    order_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate(self, attrs):
        if not attrs.get("wallet_token") and not attrs.get("member_number"):
            raise serializers.ValidationError("wallet_token oder member_number ist erforderlich.")
        return attrs


class MeSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField(allow_blank=True)
    platform_admin = serializers.BooleanField()
    memberships = serializers.ListField()
    wallets = WalletSerializer(many=True)

    @classmethod
    def from_user(cls, user):
        memberships = Membership.objects.select_related("business").filter(user=user, is_active=True)
        return {
            "username": user.username,
            "email": user.email,
            "platform_admin": user.is_staff or user.is_superuser,
            "memberships": [
                {"business": BusinessSerializer(item.business).data, "role": item.role}
                for item in memberships
            ],
            "wallets": user.apluspay_wallets.select_related("business").all(),
        }
