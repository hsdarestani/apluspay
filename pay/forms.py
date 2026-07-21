from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import BusinessSettings, LedgerEntry, Location, Membership, Offer, Plan, VendorApp, Wallet

User = get_user_model()


class StyledFormMixin:
    def apply_styles(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
            field.widget.attrs.setdefault("placeholder", field.label)


class CustomerRegistrationForm(StyledFormMixin, UserCreationForm):
    email = forms.EmailField(label="E-Mail-Adresse")
    first_name = forms.CharField(label="Vorname", max_length=80)
    last_name = forms.CharField(label="Nachname", max_length=80)
    phone = forms.CharField(label="Telefonnummer", max_length=40, required=False)
    marketing_opt_in = forms.BooleanField(label="Ich möchte Angebote und Neuigkeiten erhalten", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name", "phone", "password1", "password2", "marketing_opt_in")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Benutzername"
        self.fields["password1"].label = "Passwort"
        self.fields["password2"].label = "Passwort wiederholen"
        self.apply_styles()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Für diese E-Mail-Adresse existiert bereits ein Konto.")
        return email


class BusinessProvisionForm(StyledFormMixin, forms.Form):
    business_name = forms.CharField(label="Unternehmensname", max_length=140)
    slug = forms.SlugField(label="Mandantenkennung", help_text="Zum Beispiel: cafe-zentrale")
    category = forms.CharField(label="Kategorie", max_length=80, initial="Gastronomie")
    owner_username = forms.CharField(label="Benutzername des Betreibers", max_length=150)
    owner_email = forms.EmailField(label="E-Mail-Adresse des Betreibers")
    owner_password = forms.CharField(label="Anfangspasswort", widget=forms.PasswordInput, min_length=10)
    plan = forms.ModelChoiceField(label="Tarif", queryset=Plan.objects.filter(is_active=True))
    location_name = forms.CharField(label="Erster Standort", initial="Hauptstandort", max_length=120)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean_owner_username(self):
        value = self.cleaned_data["owner_username"]
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return value


class StaffCreateForm(StyledFormMixin, forms.Form):
    username = forms.CharField(label="Benutzername", max_length=150)
    email = forms.EmailField(label="E-Mail-Adresse", required=False)
    password = forms.CharField(label="Anfangspasswort", widget=forms.PasswordInput, min_length=10)
    role = forms.ChoiceField(
        label="Rolle",
        choices=[
            (Membership.Role.MANAGER, "Leitung"),
            (Membership.Role.STAFF, "Mitarbeiter"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return value


class CustomerCreateForm(StyledFormMixin, forms.Form):
    username = forms.CharField(label="Kunden-Benutzername", max_length=150)
    display_name = forms.CharField(label="Anzeigename", max_length=140)
    email = forms.EmailField(label="E-Mail-Adresse")
    phone = forms.CharField(label="Telefonnummer", max_length=40, required=False)
    password = forms.CharField(label="Anfangspasswort", widget=forms.PasswordInput, min_length=10)
    initial_balance = forms.DecimalField(label="Startguthaben", min_value=0, decimal_places=2, initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return value


class PaymentRequestForm(StyledFormMixin, forms.Form):
    member_number = forms.CharField(label="Mitgliedsnummer", max_length=8)
    amount = forms.DecimalField(label="Betrag", min_value=0.01, decimal_places=2)
    tip_percentage = forms.DecimalField(label="Trinkgeld in Prozent", min_value=0, max_value=100, decimal_places=2, initial=0)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellreferenz", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


MoneyActionForm = PaymentRequestForm


class WalletMoneyForm(StyledFormMixin, forms.Form):
    action = forms.ChoiceField(label="Buchungsart", choices=[(LedgerEntry.Type.TOPUP, "Aufladen"), (LedgerEntry.Type.REFUND, "Erstatten")])
    amount = forms.DecimalField(label="Betrag", min_value=0.01, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Referenz", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class OfferForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["title", "body", "image_url", "target_tier", "starts_at", "ends_at", "is_active"]
        labels = {
            "title": "Titel",
            "body": "Beschreibung",
            "image_url": "Bildadresse",
            "target_tier": "Zielgruppe",
            "starts_at": "Beginn",
            "ends_at": "Ende",
            "is_active": "Veröffentlicht",
        }
        widgets = {"starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}), "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class BusinessSettingsForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BusinessSettings
        fields = ["require_customer_confirmation", "tip_option_1", "tip_option_2", "tip_option_3", "tip_option_4", "gold_threshold", "platinum_threshold", "birthday_bonus", "loyalty_enabled", "reviews_enabled", "offers_enabled"]
        labels = {
            "require_customer_confirmation": "Bestätigung durch den Kunden erforderlich",
            "tip_option_1": "Trinkgeld-Auswahl 1 in Prozent",
            "tip_option_2": "Trinkgeld-Auswahl 2 in Prozent",
            "tip_option_3": "Trinkgeld-Auswahl 3 in Prozent",
            "tip_option_4": "Trinkgeld-Auswahl 4 in Prozent",
            "gold_threshold": "Grenze für Gold",
            "platinum_threshold": "Grenze für Platin",
            "birthday_bonus": "Geburtstagsbonus",
            "loyalty_enabled": "Treuepunkte aktivieren",
            "reviews_enabled": "Bewertungen aktivieren",
            "offers_enabled": "Angebote aktivieren",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class VendorAppForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = VendorApp
        fields = ["mode", "app_name", "icon_url", "web_url", "ios_url", "android_url", "deep_link", "public_client_id", "show_in_apluspay", "shared_identity_enabled", "external_registration_enabled"]
        labels = {
            "mode": "Art der Anbindung",
            "app_name": "Name der eigenen App",
            "icon_url": "Adresse des App-Symbols",
            "web_url": "Webadresse",
            "ios_url": "Adresse im App Store",
            "android_url": "Adresse im Play Store",
            "deep_link": "Direktlink zur App",
            "public_client_id": "Öffentliche Client-Kennung",
            "show_in_apluspay": "In A+Pay anzeigen",
            "shared_identity_enabled": "Gemeinsame Anmeldung aktivieren",
            "external_registration_enabled": "Registrierung über die eigene App erlauben",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mode"].choices = [
            (VendorApp.Mode.NONE, "Keine eigene App"),
            (VendorApp.Mode.LINK, "Externer Link oder Direktlink"),
            (VendorApp.Mode.SHARED_API, "Gemeinsame A+Pay-Schnittstelle"),
            (VendorApp.Mode.SSO, "Gemeinsame Anmeldung"),
        ]
        self.apply_styles()


class LocationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "slug", "address", "google_review_url", "instagram_url", "tiktok_url", "is_active"]
        labels = {
            "name": "Standortname",
            "slug": "Standortkennung",
            "address": "Adresse",
            "google_review_url": "Adresse für Google-Bewertungen",
            "instagram_url": "Instagram-Adresse",
            "tiktok_url": "TikTok-Adresse",
            "is_active": "Standort aktiv",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class WalletStatusForm(forms.Form):
    status = forms.ChoiceField(label="Status", choices=Wallet.Status.choices)
