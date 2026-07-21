import base64
import hashlib
import json
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import MemberProfile

User = get_user_model()
APPLE_AUTHORIZATION_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


class AppleLoginError(Exception):
    pass


def apple_login_is_configured():
    private_key_available = bool(settings.APPLE_PRIVATE_KEY or settings.APPLE_PRIVATE_KEY_BASE64)
    return all(
        [
            settings.APPLE_CLIENT_ID,
            settings.APPLE_TEAM_ID,
            settings.APPLE_KEY_ID,
            settings.APPLE_REDIRECT_URI,
            private_key_available,
        ]
    )


def _private_key():
    if settings.APPLE_PRIVATE_KEY_BASE64:
        try:
            return base64.b64decode(settings.APPLE_PRIVATE_KEY_BASE64).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise AppleLoginError("Der private Apple-Schlüssel ist ungültig konfiguriert.") from exc
    return settings.APPLE_PRIVATE_KEY.replace("\\n", "\n")


def _client_secret():
    now = int(time.time())
    payload = {
        "iss": settings.APPLE_TEAM_ID,
        "iat": now,
        "exp": now + 300,
        "aud": APPLE_ISSUER,
        "sub": settings.APPLE_CLIENT_ID,
    }
    try:
        return jwt.encode(
            payload,
            _private_key(),
            algorithm="ES256",
            headers={"kid": settings.APPLE_KEY_ID},
        )
    except Exception as exc:
        raise AppleLoginError("Der Apple-Client-Schlüssel konnte nicht erzeugt werden.") from exc


def exchange_code_for_claims(*, code, nonce):
    request_data = urlencode(
        {
            "client_id": settings.APPLE_CLIENT_ID,
            "client_secret": _client_secret(),
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.APPLE_REDIRECT_URI,
        }
    ).encode("utf-8")
    request = Request(
        APPLE_TOKEN_URL,
        data=request_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=15) as response:
            token_payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise AppleLoginError("Apple hat die Anmeldung abgelehnt. Bitte versuche es erneut.") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AppleLoginError("Die Verbindung zu Apple ist derzeit nicht möglich.") from exc

    identity_token = token_payload.get("id_token")
    if not identity_token:
        raise AppleLoginError("Apple hat kein gültiges Identitätstoken zurückgegeben.")

    try:
        key_client = jwt.PyJWKClient(APPLE_KEYS_URL, cache_keys=True)
        signing_key = key_client.get_signing_key_from_jwt(identity_token)
        claims = jwt.decode(
            identity_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID,
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        raise AppleLoginError("Die Apple-Identität konnte nicht sicher bestätigt werden.") from exc

    token_nonce = claims.get("nonce", "")
    if not nonce or not token_nonce or not secrets.compare_digest(str(token_nonce), str(nonce)):
        raise AppleLoginError("Die Apple-Anmeldung konnte nicht eindeutig deiner Sitzung zugeordnet werden.")
    return claims


def _boolean_claim(value):
    return value is True or str(value).lower() == "true"


def _name_from_payload(raw_user):
    if not raw_user:
        return "", ""
    try:
        payload = json.loads(raw_user)
    except json.JSONDecodeError:
        return "", ""
    name = payload.get("name") or {}
    return (name.get("firstName") or "").strip(), (name.get("lastName") or "").strip()


def _customer_for_apple_claims(*, claims, raw_user=""):
    subject = claims.get("sub", "").strip()
    email = (claims.get("email") or "").strip().lower()
    if not subject:
        raise AppleLoginError("Apple hat keine eindeutige Benutzerkennung geliefert.")
    if not email or not _boolean_claim(claims.get("email_verified")):
        raise AppleLoginError("Apple hat keine bestätigte E-Mail-Adresse geliefert.")

    deterministic_username = f"apple_{hashlib.sha256(subject.encode('utf-8')).hexdigest()[:24]}"
    user = User.objects.filter(username=deterministic_username).first()
    if user is None:
        user = User.objects.filter(email__iexact=email).order_by("id").first()

    if user and (user.is_staff or user.is_superuser or user.apluspay_memberships.filter(is_active=True).exists()):
        raise AppleLoginError("Mitarbeiter- und Betreiberkonten müssen sich mit Benutzername und Passwort anmelden.")

    first_name, last_name = _name_from_payload(raw_user)
    if user is None:
        user = User(
            username=deterministic_username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        user.set_unusable_password()
        user.save()
    else:
        changed_fields = []
        if not user.email:
            user.email = email
            changed_fields.append("email")
        if first_name and not user.first_name:
            user.first_name = first_name
            changed_fields.append("first_name")
        if last_name and not user.last_name:
            user.last_name = last_name
            changed_fields.append("last_name")
        if changed_fields:
            user.save(update_fields=changed_fields)

    profile, _ = MemberProfile.objects.get_or_create(user=user)
    if not profile.display_name:
        profile.display_name = user.get_full_name() or email.split("@", 1)[0]
        profile.save(update_fields=["display_name"])
    return user


def apple_login_start(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if not apple_login_is_configured():
        messages.error(request, "Die Apple-Anmeldung ist noch nicht vollständig eingerichtet.")
        return redirect("login")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    request.session["apple_login_state"] = state
    request.session["apple_login_nonce"] = nonce
    requested_next = request.GET.get("next", "")
    if requested_next and url_has_allowed_host_and_scheme(
        requested_next,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        request.session["apple_login_next"] = requested_next

    query = urlencode(
        {
            "client_id": settings.APPLE_CLIENT_ID,
            "redirect_uri": settings.APPLE_REDIRECT_URI,
            "response_type": "code",
            "response_mode": "form_post",
            "scope": "name email",
            "state": state,
            "nonce": nonce,
        }
    )
    return redirect(f"{APPLE_AUTHORIZATION_URL}?{query}")


@csrf_exempt
@require_POST
def apple_login_callback(request):
    expected_state = request.session.pop("apple_login_state", "")
    nonce = request.session.pop("apple_login_nonce", "")
    received_state = request.POST.get("state", "")
    if not expected_state or not received_state or not secrets.compare_digest(expected_state, received_state):
        messages.error(request, "Die Apple-Anmeldung ist abgelaufen oder ungültig. Bitte starte sie erneut.")
        return redirect("login")

    if request.POST.get("error"):
        messages.info(request, "Die Apple-Anmeldung wurde abgebrochen.")
        return redirect("login")

    code = request.POST.get("code", "")
    if not code:
        messages.error(request, "Apple hat keinen gültigen Anmeldecode geliefert.")
        return redirect("login")

    try:
        claims = exchange_code_for_claims(code=code, nonce=nonce)
        user = _customer_for_apple_claims(claims=claims, raw_user=request.POST.get("user", ""))
    except AppleLoginError as exc:
        messages.error(request, str(exc))
        return redirect("login")

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    messages.success(request, "Du bist jetzt sicher mit Apple angemeldet.")
    destination = request.session.pop("apple_login_next", "") or reverse("customer-dashboard")
    return redirect(destination)
