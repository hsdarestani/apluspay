from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Business, BusinessSettings, CustomerVendorEnrollment, LedgerEntry, Membership, PaymentRequest, Plan, VendorApp, Wallet
from .services import create_payment_request, create_staff_member, enroll_customer, post_wallet_entry, provision_business, require_role

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

    def test_manager_cannot_create_another_manager(self):
        manager = User.objects.create_user("manager-a", password="strong-pass-123")
        Membership.objects.create(user=manager, business=self.business_a, role=Membership.Role.MANAGER)
        with self.assertRaises(PermissionDenied):
            create_staff_member(business=self.business_a, username="manager-b", email="manager-b@example.com", password="strong-pass-123", role=Membership.Role.MANAGER, actor=manager)


class CentralCustomerFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("customer", email="customer@example.com", password="strong-pass-123", first_name="Alex")
        self.vendor = Business.objects.create(name="SAMS", slug="sams", status=Business.Status.ACTIVE, is_discoverable=True)
        BusinessSettings.objects.create(business=self.vendor)
        VendorApp.objects.create(business=self.vendor, mode=VendorApp.Mode.NONE)

    def test_customer_without_vendor_can_open_central_dashboard(self):
        self.client.login(username="customer", password="strong-pass-123")
        response = self.client.get(reverse("customer-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SAMS")

    def test_customer_can_join_vendor_once(self):
        self.client.login(username="customer", password="strong-pass-123")
        response = self.client.post(reverse("join-vendor", args=[self.vendor.slug]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Wallet.objects.filter(owner=self.user, business=self.vendor).count(), 1)
        self.assertEqual(CustomerVendorEnrollment.objects.filter(user=self.user, business=self.vendor).count(), 1)
        self.client.post(reverse("join-vendor", args=[self.vendor.slug]))
        self.assertEqual(Wallet.objects.filter(owner=self.user, business=self.vendor).count(), 1)

    def test_vendor_does_not_need_dedicated_app(self):
        _, wallet = enroll_customer(user=self.user, business=self.vendor)
        self.assertIsNotNone(wallet)
        self.assertEqual(self.vendor.vendor_app.mode, VendorApp.Mode.NONE)

    def test_dedicated_app_metadata_is_optional_and_visible_in_api(self):
        self.vendor.vendor_app.mode = VendorApp.Mode.SHARED_API
        self.vendor.vendor_app.app_name = "SAMS App"
        self.vendor.vendor_app.web_url = "https://sams.example/app"
        self.vendor.vendor_app.shared_identity_enabled = True
        self.vendor.vendor_app.save()
        self.client.login(username="customer", password="strong-pass-123")
        response = self.client.get(reverse("api-vendors"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["vendor_app"]["app_name"], "SAMS App")


class PaymentConfirmationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="strong-pass-123")
        self.customer = User.objects.create_user("buyer", password="strong-pass-123")
        self.business = Business.objects.create(name="Café", slug="cafe", status=Business.Status.ACTIVE)
        BusinessSettings.objects.create(business=self.business, require_customer_confirmation=True)
        Membership.objects.create(user=self.staff, business=self.business, role=Membership.Role.STAFF)
        _, self.wallet = enroll_customer(user=self.customer, business=self.business)
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="100.00", actor=self.staff)

    def test_staff_request_waits_for_customer_and_tip_is_separate(self):
        payment = create_payment_request(wallet=self.wallet, amount="20.00", tip_percentage="10", actor=self.staff)
        self.assertEqual(payment.status, PaymentRequest.Status.PENDING)
        self.client.login(username="buyer", password="strong-pass-123")
        response = self.client.post(reverse("customer-payment-action", args=[payment.pk]), {"action": "confirm"})
        self.assertEqual(response.status_code, 302)
        payment.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(payment.status, PaymentRequest.Status.CONFIRMED)
        self.assertEqual(payment.tip_amount, Decimal("2.00"))
        self.assertEqual(self.wallet.balance, Decimal("78.00"))
        self.assertEqual(payment.ledger_entries.filter(entry_type=LedgerEntry.Type.PURCHASE).count(), 1)
        self.assertEqual(payment.ledger_entries.filter(entry_type=LedgerEntry.Type.TIP).count(), 1)

    def test_other_customer_cannot_confirm_payment(self):
        stranger = User.objects.create_user("stranger", password="strong-pass-123")
        payment = create_payment_request(wallet=self.wallet, amount="10.00", tip_percentage="0", actor=self.staff)
        self.client.login(username="stranger", password="strong-pass-123")
        response = self.client.post(reverse("customer-payment-action", args=[payment.pk]), {"action": "confirm"})
        self.assertEqual(response.status_code, 404)


class WalletLedgerTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user("actor", password="strong-pass-123")
        self.business = Business.objects.create(name="Café", slug="ledger-cafe", status=Business.Status.ACTIVE)
        self.wallet = Wallet.objects.create(business=self.business, display_name="Customer")

    def test_balance_is_derived_from_immutable_entries(self):
        post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.TOPUP, amount="50.00", actor=self.actor)
        purchase = post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount="12.50", actor=self.actor)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("37.50"))
        self.assertEqual(purchase.balance_before, Decimal("50.00"))
        self.assertEqual(purchase.balance_after, Decimal("37.50"))

    def test_negative_balance_is_rejected(self):
        with self.assertRaises(ValidationError):
            post_wallet_entry(wallet=self.wallet, entry_type=LedgerEntry.Type.PURCHASE, amount="1.00", actor=self.actor)


class PlatformProvisioningTests(TestCase):
    def test_platform_can_provision_complete_vendor(self):
        plan = Plan.objects.create(code="starter", name="Starter", monthly_price="49.00")
        business, owner = provision_business(business_name="New Café", slug="new-cafe", category="Café", owner_username="new-owner", owner_email="owner@example.com", owner_password="strong-pass-123", plan=plan, location_name="Main")
        self.assertTrue(Membership.objects.filter(user=owner, business=business, role=Membership.Role.OWNER).exists())
        self.assertEqual(business.locations.count(), 1)
        self.assertEqual(business.subscription.plan, plan)
        self.assertTrue(hasattr(business, "app_settings"))
        self.assertTrue(hasattr(business, "vendor_app"))
