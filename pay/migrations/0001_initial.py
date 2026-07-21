import django.db.models.deletion
import pay.models
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Business",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=140)),
                ("slug", models.SlugField(unique=True)),
                ("legal_name", models.CharField(blank=True, max_length=180)),
                ("vat_id", models.CharField(blank=True, max_length=40)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("currency", models.CharField(default="EUR", max_length=3)),
                ("primary_color", models.CharField(default="#F5B800", max_length=7)),
                ("status", models.CharField(choices=[("TRIAL", "Testphase"), ("ACTIVE", "Aktiv"), ("SUSPENDED", "Gesperrt")], default="TRIAL", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Plan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=80)),
                ("monthly_price", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=9)),
                ("max_locations", models.PositiveIntegerField(default=1)),
                ("max_staff", models.PositiveIntegerField(default=5)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["monthly_price", "name"]},
        ),
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("slug", models.SlugField()),
                ("address", models.CharField(blank=True, max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="locations", to="pay.business")),
            ],
            options={"ordering": ["business__name", "name"]},
        ),
        migrations.CreateModel(
            name="Membership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("OWNER", "Owner"), ("MANAGER", "Manager"), ("STAFF", "Staff")], max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="pay.business")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="apluspay_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["business__name", "user__username"]},
        ),
        migrations.CreateModel(
            name="Subscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("TRIAL", "Testphase"), ("ACTIVE", "Aktiv"), ("PAST_DUE", "Überfällig"), ("CANCELLED", "Gekündigt")], default="TRIAL", max_length=16)),
                ("trial_ends_at", models.DateTimeField(blank=True, null=True)),
                ("current_period_ends_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="subscription", to="pay.business")),
                ("plan", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="subscriptions", to="pay.plan")),
            ],
        ),
        migrations.CreateModel(
            name="Wallet",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("member_number", models.CharField(db_index=True, default=pay.models.generate_member_number, editable=False, max_length=8)),
                ("display_name", models.CharField(max_length=140)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("qr_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("status", models.CharField(choices=[("ACTIVE", "Aktiv"), ("BLOCKED", "Gesperrt"), ("CLOSED", "Geschlossen")], default="ACTIVE", max_length=12)),
                ("balance", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("loyalty_points", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="wallets", to="pay.business")),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="wallets", to="pay.location")),
                ("owner", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="apluspay_wallets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["display_name"]},
        ),
        migrations.CreateModel(
            name="LedgerEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("bill_number", models.CharField(db_index=True, default=pay.models.generate_bill_number, editable=False, max_length=32, unique=True)),
                ("entry_type", models.CharField(choices=[("TOPUP", "Aufladung"), ("PURCHASE", "Einkauf"), ("REFUND", "Erstattung"), ("BONUS", "Bonus"), ("ADJUSTMENT", "Korrektur")], max_length=16)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("balance_before", models.DecimalField(decimal_places=2, max_digits=12)),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=12)),
                ("description", models.CharField(blank=True, max_length=255)),
                ("order_reference", models.CharField(blank=True, max_length=100)),
                ("idempotency_key", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="pay.business")),
                ("location", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ledger_entries", to="pay.location")),
                ("performed_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="apluspay_ledger_entries", to=settings.AUTH_USER_MODEL)),
                ("wallet", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ledger_entries", to="pay.wallet")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=80)),
                ("object_type", models.CharField(max_length=80)),
                ("object_id", models.CharField(max_length=80)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="apluspay_audit_events", to=settings.AUTH_USER_MODEL)),
                ("business", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="audit_events", to="pay.business")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(model_name="location", constraint=models.UniqueConstraint(fields=("business", "slug"), name="unique_location_slug_per_business")),
        migrations.AddConstraint(model_name="membership", constraint=models.UniqueConstraint(fields=("user", "business"), name="unique_apluspay_membership")),
        migrations.AddConstraint(model_name="wallet", constraint=models.UniqueConstraint(fields=("business", "member_number"), name="unique_member_number_per_business")),
        migrations.AddConstraint(model_name="wallet", constraint=models.UniqueConstraint(condition=models.Q(("owner__isnull", False)), fields=("business", "owner"), name="unique_customer_wallet_per_business")),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["business", "created_at"], name="pay_ledger_biz_date_idx")),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["wallet", "created_at"], name="pay_ledger_wallet_date_idx")),
        migrations.AddIndex(model_name="ledgerentry", index=models.Index(fields=["order_reference"], name="pay_ledger_order_ref_idx")),
        migrations.AddConstraint(model_name="ledgerentry", constraint=models.CheckConstraint(condition=models.Q(("amount", 0), _negated=True), name="apluspay_ledger_amount_not_zero")),
        migrations.AddConstraint(model_name="ledgerentry", constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key", ""), _negated=True), fields=("business", "idempotency_key"), name="unique_apluspay_business_idempotency_key")),
        migrations.AddIndex(model_name="auditevent", index=models.Index(fields=["business", "created_at"], name="pay_audit_biz_date_idx")),
    ]
