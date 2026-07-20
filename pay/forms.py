from django import forms
from django.contrib.auth import get_user_model

from .models import LedgerEntry, Membership, Plan, Wallet

User = get_user_model()


class StyledFormMixin:
    def apply_styles(self):
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class BusinessProvisionForm(StyledFormMixin, forms.Form):
    business_name = forms.CharField(label="Unternehmensname", max_length=140)
    slug = forms.SlugField(label="Mandanten-ID", help_text="z. B. cafe-central")
    owner_username = forms.CharField(label="Owner Benutzername", max_length=150)
    owner_email = forms.EmailField(label="Owner E-Mail")
    owner_password = forms.CharField(label="Initialpasswort", widget=forms.PasswordInput, min_length=10)
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
    email = forms.EmailField(label="E-Mail", required=False)
    password = forms.CharField(label="Initialpasswort", widget=forms.PasswordInput, min_length=10)
    role = forms.ChoiceField(
        label="Rolle",
        choices=[
            (Membership.Role.MANAGER, Membership.Role.MANAGER.label),
            (Membership.Role.STAFF, Membership.Role.STAFF.label),
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
    username = forms.CharField(label="Kunden-Login", max_length=150)
    display_name = forms.CharField(label="Name", max_length=140)
    email = forms.EmailField(label="E-Mail")
    phone = forms.CharField(label="Telefon", max_length=40, required=False)
    password = forms.CharField(label="Initialpasswort", widget=forms.PasswordInput, min_length=10)
    initial_balance = forms.DecimalField(label="Startguthaben", min_value=0, decimal_places=2, initial=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()

    def clean_username(self):
        value = self.cleaned_data["username"]
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError("Dieser Benutzername ist bereits vergeben.")
        return value


class MoneyActionForm(StyledFormMixin, forms.Form):
    member_number = forms.CharField(label="Mitgliedsnummer", max_length=8)
    amount = forms.DecimalField(label="Betrag", min_value=0.01, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Bestellreferenz", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class WalletMoneyForm(StyledFormMixin, forms.Form):
    action = forms.ChoiceField(choices=[(LedgerEntry.Type.TOPUP, "Aufladen"), (LedgerEntry.Type.REFUND, "Erstatten")])
    amount = forms.DecimalField(label="Betrag", min_value=0.01, decimal_places=2)
    description = forms.CharField(label="Beschreibung", max_length=255, required=False)
    order_reference = forms.CharField(label="Referenz", max_length=100, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_styles()


class WalletStatusForm(forms.Form):
    status = forms.ChoiceField(choices=Wallet.Status.choices)
