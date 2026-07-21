import django.db.models.deletion
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


def create_platform_defaults(apps, schema_editor):
    Business = apps.get_model("pay", "Business")
    BusinessSettings = apps.get_model("pay", "BusinessSettings")
    VendorApp = apps.get_model("pay", "VendorApp")
    Enrollment = apps.get_model("pay", "CustomerVendorEnrollment")
    Wallet = apps.get_model("pay", "Wallet")
    for business in Business.objects.all():
        BusinessSettings.objects.get_or_create(business=business)
        VendorApp.objects.get_or_create(business=business)
    for wallet in Wallet.objects.exclude(owner_id=None):
        Enrollment.objects.get_or_create(user_id=wallet.owner_id, business_id=wallet.business_id, defaults={"source": "STAFF", "is_active": True})


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pay", "0001_initial"),
    ]

    operations = [
        migrations.AddField(model_name="business", name="category", field=models.CharField(blank=True, default="Hospitality", max_length=80)),
        migrations.AddField(model_name="business", name="cover_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="business", name="description", field=models.TextField(blank=True)),
        migrations.AddField(model_name="business", name="is_discoverable", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="business", name="logo_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="location", name="google_review_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="location", name="instagram_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="location", name="position", field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="location", name="tiktok_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="membership", name="can_manage_content", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="wallet", name="monthly_topup_total", field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
        migrations.AddField(model_name="wallet", name="tier", field=models.CharField(choices=[("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platinum")], default="SILVER", max_length=12)),
        migrations.AlterField(model_name="ledgerentry", name="entry_type", field=models.CharField(choices=[("TOPUP", "Aufladung"), ("PURCHASE", "Einkauf"), ("TIP", "Trinkgeld"), ("REFUND", "Erstattung"), ("BONUS", "Bonus"), ("ADJUSTMENT", "Korrektur")], max_length=16)),
        migrations.CreateModel(
            name="BusinessSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("require_customer_confirmation", models.BooleanField(default=True)),
                ("tip_option_1", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("tip_option_2", models.DecimalField(decimal_places=2, default=Decimal("5.00"), max_digits=5)),
                ("tip_option_3", models.DecimalField(decimal_places=2, default=Decimal("10.00"), max_digits=5)),
                ("tip_option_4", models.DecimalField(decimal_places=2, default=Decimal("15.00"), max_digits=5)),
                ("tip_allocation", models.CharField(choices=[("TEAM", "Team"), ("EMPLOYEE", "Einzelne Person")], default="TEAM", max_length=12)),
                ("gold_threshold", models.DecimalField(decimal_places=2, default=Decimal("500.00"), max_digits=12)),
                ("platinum_threshold", models.DecimalField(decimal_places=2, default=Decimal("700.00"), max_digits=12)),
                ("birthday_bonus", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("loyalty_enabled", models.BooleanField(default=True)),
                ("reviews_enabled", models.BooleanField(default=True)),
                ("offers_enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="app_settings", to="pay.business")),
            ],
        ),
        migrations.CreateModel(
            name="VendorApp",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("NONE", "Keine eigene App"), ("LINK", "Externer Link / Deep Link"), ("SHARED_API", "Gemeinsame A+Pay API"), ("SSO", "Shared Identity / SSO")], default="NONE", max_length=16)),
                ("app_name", models.CharField(blank=True, max_length=120)),
                ("icon_url", models.URLField(blank=True)),
                ("web_url", models.URLField(blank=True)),
                ("ios_url", models.URLField(blank=True)),
                ("android_url", models.URLField(blank=True)),
                ("deep_link", models.CharField(blank=True, max_length=255)),
                ("public_client_id", models.CharField(blank=True, max_length=80)),
                ("show_in_apluspay", models.BooleanField(default=True)),
                ("shared_identity_enabled", models.BooleanField(default=False)),
                ("external_registration_enabled", models.BooleanField(default=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="vendor_app", to="pay.business")),
            ],
        ),
        migrations.CreateModel(
            name="MemberProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, max_length=140)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("birth_date", models.DateField(blank=True, null=True)),
                ("age_confirmed", models.BooleanField(default=False)),
                ("marketing_opt_in", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="apluspay_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="CustomerVendorEnrollment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("APLUSPAY", "A+Pay"), ("DEDICATED_APP", "Vendor App"), ("API", "API"), ("STAFF", "Staff")], default="APLUSPAY", max_length=20)),
                ("external_customer_id", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="customer_enrollments", to="pay.business")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="vendor_enrollments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-joined_at"]},
        ),
        migrations.AddConstraint(model_name="customervendorenrollment", constraint=models.UniqueConstraint(fields=("user", "business"), name="unique_customer_vendor_enrollment")),
        migrations.CreateModel(
            name="PaymentRequest",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("base_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("tip_percentage", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=5)),
                ("tip_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("order_reference", models.CharField(blank=True, max_length=100)),
                ("customer_confirmation_required", models.BooleanField(default=True)),
                ("status", models.CharField(choices=[("PENDING", "Wartet auf Bestätigung"), ("CONFIRMED", "Bestätigt"), ("CANCELLED", "Storniert"), ("EXPIRED", "Abgelaufen")], default="PENDING", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="pay.business")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="apluspay_created_payment_requests", to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="payment_requests", to="pay.location")),
                ("purchase_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_payment_request", to="pay.ledgerentry")),
                ("tip_entry", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="tip_payment_request", to="pay.ledgerentry")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_requests", to="pay.wallet")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="paymentrequest", index=models.Index(fields=["wallet", "status", "created_at"], name="pay_req_wallet_status_idx")),
        migrations.AddIndex(model_name="paymentrequest", index=models.Index(fields=["business", "location", "created_at"], name="pay_req_biz_loc_idx")),
        migrations.AddField(model_name="ledgerentry", name="payment_request", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ledger_entries", to="pay.paymentrequest")),
        migrations.CreateModel(
            name="Offer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=180)),
                ("body", models.TextField()),
                ("image_url", models.URLField(blank=True)),
                ("target_tier", models.CharField(choices=[("ALL", "Alle"), ("SILVER", "Silber"), ("GOLD", "Gold"), ("PLATINUM", "Platinum")], default="ALL", max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("starts_at", models.DateTimeField(blank=True, null=True)),
                ("ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="pay.business")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="apluspay_created_offers", to=settings.AUTH_USER_MODEL)),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="pay.location")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ReviewStatus",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("location", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_statuses", to="pay.location")),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="review_statuses", to="pay.wallet")),
            ],
        ),
        migrations.AddConstraint(model_name="reviewstatus", constraint=models.UniqueConstraint(fields=("wallet", "location"), name="unique_wallet_location_review")),
        migrations.CreateModel(
            name="AppNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("PAYMENT", "Zahlung"), ("OFFER", "Angebot"), ("BIRTHDAY", "Geburtstag"), ("SYSTEM", "System")], default="SYSTEM", max_length=16)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField()),
                ("data", models.JSONField(blank=True, default=dict)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="pay.business")),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="pay.location")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="apluspay_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="appnotification", index=models.Index(fields=["recipient", "is_read", "created_at"], name="pay_notif_rec_read_idx")),
        migrations.CreateModel(
            name="PushDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("platform", models.CharField(choices=[("IOS", "iOS"), ("ANDROID", "Android"), ("WEB", "Web")], max_length=12)),
                ("token", models.CharField(max_length=512, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="apluspay_push_devices", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(create_platform_defaults, migrations.RunPython.noop),
    ]
