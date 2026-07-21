from decimal import Decimal

from rest_framework import serializers

from .models import AppNotification, Business, LedgerEntry, Membership, Offer, PaymentRequest, PushDevice, VendorApp, Wallet


class VendorAppSerializer(serializers.ModelSerializer):
    enabled = serializers.BooleanField(source="is_enabled", read_only=True)

    class Meta:
        model = VendorApp
        fields = ["mode", "app_name", "icon_url", "web_url", "ios_url", "android_url", "deep_link", "public_client_id", "show_in_apluspay", "shared_identity_enabled", "external_registration_enabled", "enabled"]


class BusinessSerializer(serializers.ModelSerializer):
    vendor_app = serializers.SerializerMethodField()

    def get_vendor_app(self, obj):
        try:
            vendor_app = obj.vendor_app
        except VendorApp.DoesNotExist:
            return None
        return VendorAppSerializer(vendor_app).data

    class Meta:
        model = Business
        fields = ["id", "name", "slug", "currency", "primary_color", "category", "description", "logo_url", "cover_url", "status", "vendor_app"]


class WalletSerializer(serializers.ModelSerializer):
    business = BusinessSerializer(read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "business", "member_number", "display_name", "status", "tier", "balance", "monthly_topup_total", "loyalty_points", "qr_token", "updated_at"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ["id", "bill_number", "entry_type", "amount", "balance_before", "balance_after", "description", "order_reference", "created_at"]


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = ["id", "title", "body", "image_url", "target_tier", "starts_at", "ends_at", "created_at"]


class PaymentRequestSerializer(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PaymentRequest
        fields = ["id", "base_amount", "tip_percentage", "tip_amount", "total_amount", "description", "order_reference", "status", "expires_at", "created_at"]


class MoneyActionSerializer(serializers.Serializer):
    wallet_token = serializers.UUIDField(required=False)
    member_number = serializers.CharField(max_length=8, required=False)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    tip_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        required=False,
        default=Decimal("0.00"),
    )
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
            "memberships": [{"business": BusinessSerializer(item.business).data, "role": item.role} for item in memberships],
            "wallets": user.apluspay_wallets.select_related("business").all(),
        }


class NotificationSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source="business.name", read_only=True)
    business_slug = serializers.CharField(source="business.slug", read_only=True)

    class Meta:
        model = AppNotification
        fields = ["id", "business_name", "business_slug", "kind", "title", "body", "data", "is_read", "created_at"]


class PushDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushDevice
        fields = ["platform", "token", "is_active", "updated_at"]
        read_only_fields = ["updated_at"]
