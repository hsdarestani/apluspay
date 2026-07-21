import re
from html.parser import HTMLParser

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Business, BusinessSettings, Membership, VendorApp
from .services import enroll_customer

User = get_user_model()


class VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


def visible_text(response):
    parser = VisibleTextParser()
    parser.feed(response.content.decode("utf-8"))
    return parser.text()


class GermanInterfaceTests(TestCase):
    forbidden_words = {
        "Login",
        "Logout",
        "Welcome",
        "Owner",
        "Staff",
        "Customer",
        "Wallet",
        "Vendor",
        "Offers",
        "Transactions",
        "Payment",
        "Connected",
        "Discover",
        "Activity",
        "Manage",
        "Overview",
        "Balance",
        "Points",
        "Home",
        "Install",
    }

    def setUp(self):
        self.business = Business.objects.create(
            name="Café Beispiel",
            slug="cafe-beispiel",
            status=Business.Status.ACTIVE,
            is_discoverable=True,
            category="Café",
        )
        BusinessSettings.objects.create(business=self.business)
        VendorApp.objects.create(business=self.business, mode=VendorApp.Mode.NONE)
        self.customer = User.objects.create_user(
            "kunde",
            email="kunde@example.com",
            password="sicheres-passwort-123",
            first_name="Anna",
        )
        self.owner = User.objects.create_user(
            "betreiber",
            email="betreiber@example.com",
            password="sicheres-passwort-123",
        )
        self.staff = User.objects.create_user(
            "mitarbeiter",
            email="mitarbeiter@example.com",
            password="sicheres-passwort-123",
        )
        Membership.objects.create(
            user=self.owner,
            business=self.business,
            role=Membership.Role.OWNER,
        )
        Membership.objects.create(
            user=self.staff,
            business=self.business,
            role=Membership.Role.STAFF,
        )
        enroll_customer(user=self.customer, business=self.business)

    def assert_german_visible_text(self, response):
        self.assertEqual(response.status_code, 200)
        text = visible_text(response)
        for word in self.forbidden_words:
            self.assertIsNone(
                re.search(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE),
                msg=f"Englisches Wort im sichtbaren Text gefunden: {word}\n{text}",
            )

    def test_public_pages_are_german(self):
        for url_name in ["landing", "login", "register"]:
            with self.subTest(url_name=url_name):
                self.assert_german_visible_text(self.client.get(reverse(url_name)))

    def test_customer_pages_are_german(self):
        self.client.login(username="kunde", password="sicheres-passwort-123")
        self.assert_german_visible_text(self.client.get(reverse("customer-dashboard")))
        self.assert_german_visible_text(
            self.client.get(reverse("customer-vendor-dashboard", args=[self.business.slug]))
        )

    def test_owner_page_is_german(self):
        self.client.login(username="betreiber", password="sicheres-passwort-123")
        self.assert_german_visible_text(
            self.client.get(reverse("owner-dashboard", args=[self.business.slug]))
        )

    def test_staff_page_is_german(self):
        self.client.login(username="mitarbeiter", password="sicheres-passwort-123")
        self.assert_german_visible_text(
            self.client.get(reverse("staff-dashboard", args=[self.business.slug]))
        )
