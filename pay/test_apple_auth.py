from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Business, Membership

User = get_user_model()

APPLE_SETTINGS = {
    "APPLE_CLIENT_ID": "de.aplus.pay.web",
    "APPLE_TEAM_ID": "TEAM123456",
    "APPLE_KEY_ID": "KEY1234567",
    "APPLE_PRIVATE_KEY": "test-key",
    "APPLE_PRIVATE_KEY_BASE64": "",
    "APPLE_REDIRECT_URI": "https://pay.smarbiz.sbs/accounts/apple/callback/",
}


class AppleLoginTests(TestCase):
    def _prepare_session(self, state="zustand", nonce="einmalwert"):
        session = self.client.session
        session["apple_login_state"] = state
        session["apple_login_nonce"] = nonce
        session.save()

    def test_login_page_contains_german_apple_button(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mit Apple fortfahren")
        self.assertContains(response, "Anmelden")
        self.assertNotContains(response, "WELCOME BACK")

    def test_unconfigured_apple_login_returns_to_login_with_german_message(self):
        response = self.client.get(reverse("apple-login"), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Die Apple-Anmeldung ist noch nicht vollständig eingerichtet.")

    @override_settings(**APPLE_SETTINGS)
    def test_apple_login_start_uses_state_nonce_and_registered_callback(self):
        response = self.client.get(reverse("apple-login"))
        self.assertEqual(response.status_code, 302)
        target = urlparse(response["Location"])
        self.assertEqual(target.netloc, "appleid.apple.com")
        query = parse_qs(target.query)
        self.assertEqual(query["client_id"], ["de.aplus.pay.web"])
        self.assertEqual(query["redirect_uri"], ["https://pay.smarbiz.sbs/accounts/apple/callback/"])
        self.assertEqual(query["response_mode"], ["form_post"])
        self.assertTrue(query["state"][0])
        self.assertTrue(query["nonce"][0])

    @override_settings(**APPLE_SETTINGS)
    @patch("pay.apple_auth.exchange_code_for_claims")
    def test_verified_apple_customer_is_created_and_logged_in(self, exchange):
        self._prepare_session()
        exchange.return_value = {
            "sub": "apple-user-123",
            "email": "kunde@privaterelay.appleid.com",
            "email_verified": "true",
            "nonce": "einmalwert",
        }
        response = self.client.post(
            reverse("apple-login-callback"),
            {
                "state": "zustand",
                "code": "einmaliger-code",
                "user": '{"name":{"firstName":"Anna","lastName":"Beispiel"}}',
            },
        )
        self.assertRedirects(response, reverse("customer-dashboard"))
        customer = User.objects.get(email="kunde@privaterelay.appleid.com")
        self.assertEqual(customer.first_name, "Anna")
        self.assertEqual(customer.last_name, "Beispiel")
        self.assertFalse(customer.has_usable_password())
        self.assertEqual(int(self.client.session["_auth_user_id"]), customer.pk)

    @override_settings(**APPLE_SETTINGS)
    @patch("pay.apple_auth.exchange_code_for_claims")
    def test_management_account_cannot_use_customer_apple_login(self, exchange):
        business = Business.objects.create(name="Café", slug="cafe", status=Business.Status.ACTIVE)
        employee = User.objects.create_user("mitarbeiter", email="team@example.com", password="sicheres-passwort")
        Membership.objects.create(user=employee, business=business, role=Membership.Role.STAFF)
        self._prepare_session()
        exchange.return_value = {
            "sub": "apple-team-123",
            "email": "team@example.com",
            "email_verified": True,
            "nonce": "einmalwert",
        }
        response = self.client.post(
            reverse("apple-login-callback"),
            {"state": "zustand", "code": "einmaliger-code"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mitarbeiter- und Betreiberkonten müssen sich mit Benutzername und Passwort anmelden.")
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(**APPLE_SETTINGS)
    def test_invalid_callback_state_is_rejected(self):
        self._prepare_session(state="richtig")
        response = self.client.post(
            reverse("apple-login-callback"),
            {"state": "falsch", "code": "einmaliger-code"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Die Apple-Anmeldung ist abgelaufen oder ungültig.")
        self.assertNotIn("_auth_user_id", self.client.session)
