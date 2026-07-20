from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from .models import Business, Membership, Plan, Wallet
from .services import post_wallet_entry, provision_business, require_role

User = get_user_model()


class MultiTenantSecurityTests(TestCase):
    def setUp(self):
        self.owner_a = User.objects.create_user("owner-a", password="strong-pass-123")
        self.owner_b = User.objects.create_user("owner-b", password="strong-pass-123")
        self.business_a = Business.objects.create(name="A", slug="a", status=Business.Status.ACTIVE)
        self.business_b = Business.objects.create(name="B", slug="b", status=Business.Status.ACTIVE)
        Membership.objects.create(user=self.owner_a, business=self.business_a, role=Membership.Role.OWNER)
        Membership.objects.create(user=self.owner_b, business=self.business_b, role=Membership.Role.OWNER)

    def test_owner_cannot_manage_another_tenant(self):
        with self.assertRaises(PermissionDenied):
            require_role(self.owner_a, self.business_b, {Membership.Role.OWNER})

    def test_wallet_lookup_is_scoped_by_business(self):
        wallet = Wallet.objects.create(business=self.business_b, display_name="B customer")
        self.client.login(username="owner-a", password="strong-pass-123")
        response = self.client.get(f"/b/{self.business_a.slug}/wallets/{wallet.pk}/")
        self.assertEqual(response.status_code, 404)


class WalletLedgerTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user("actor", password="strong-pass-123")
        self.business = Business.objects.create(name="Café", slug="cafe", status=Business.Status.ACTIVE)
        self.wallet = Wallet.objects.create(business=self.business, display_name="Customer")

    def test_balance_is_derived_from_immutable_entries(self):
        post_wallet_entry(wallet=self.wallet, entry_type="TOPUP", amount="50.00", actor=self.actor)
        purchase = post_wallet_entry(wallet=self.wallet, entry_type="PURCHASE", amount="12.50", actor=self.actor)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("37.50"))
        self.assertEqual(purchase.balance_before, Decimal("50.00"))
        self.assertEqual(purchase.balance_after, Decimal("37.50"))

    def test_negative_balance_is_rejected(self):
        with self.assertRaises(ValidationError):
            post_wallet_entry(wallet=self.wallet, entry_type="PURCHASE", amount="1.00", actor=self.actor)


class PlatformProvisioningTests(TestCase):
    def test_platform_can_provision_owner_and_tenant(self):
        plan = Plan.objects.create(code="starter", name="Starter", monthly_price="49.00")
        business, owner = provision_business(
            business_name="New Café",
            slug="new-cafe",
            owner_username="new-owner",
            owner_email="owner@example.com",
            owner_password="strong-pass-123",
            plan=plan,
            location_name="Main",
        )
        self.assertTrue(Membership.objects.filter(user=owner, business=business, role=Membership.Role.OWNER).exists())
        self.assertEqual(business.locations.count(), 1)
        self.assertEqual(business.subscription.plan, plan)
