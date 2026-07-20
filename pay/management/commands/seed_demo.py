from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from pay.models import Business, Location, Membership, Plan, Subscription, Wallet
from pay.services import post_wallet_entry

User = get_user_model()


class Command(BaseCommand):
    help = "Create a complete A+Pay multi-tenant demo."

    def handle(self, *args, **options):
        plan, _ = Plan.objects.get_or_create(
            code="starter",
            defaults={"name": "Starter", "monthly_price": Decimal("49.00"), "max_locations": 1, "max_staff": 5},
        )
        platform, created = User.objects.get_or_create(username="platform")
        platform.is_staff = True
        platform.is_superuser = True
        platform.email = "platform@aplus-solution.de"
        platform.set_password("ChangeMe123!")
        platform.save()

        business, _ = Business.objects.get_or_create(name="A+ Demo Café", slug="demo-cafe", defaults={"status": Business.Status.ACTIVE})
        location, _ = Location.objects.get_or_create(business=business, slug="main", defaults={"name": "Frankfurt Zentrum"})
        Subscription.objects.get_or_create(business=business, defaults={"plan": plan, "status": Subscription.Status.ACTIVE})

        owner, _ = User.objects.get_or_create(username="owner", defaults={"email": "owner@example.com"})
        owner.set_password("ChangeMe123!")
        owner.save()
        Membership.objects.get_or_create(user=owner, business=business, defaults={"role": Membership.Role.OWNER})

        staff, _ = User.objects.get_or_create(username="staff", defaults={"email": "staff@example.com"})
        staff.set_password("ChangeMe123!")
        staff.save()
        Membership.objects.get_or_create(user=staff, business=business, defaults={"role": Membership.Role.STAFF})

        customer, _ = User.objects.get_or_create(username="customer", defaults={"email": "customer@example.com"})
        customer.set_password("ChangeMe123!")
        customer.save()
        wallet, created = Wallet.objects.get_or_create(
            business=business,
            owner=customer,
            defaults={"location": location, "display_name": "Demo Customer", "email": customer.email},
        )
        if created:
            post_wallet_entry(wallet=wallet, entry_type="TOPUP", amount="200.00", actor=owner, description="Demo Startguthaben")

        self.stdout.write(self.style.SUCCESS("Demo ready: platform, owner, staff, customer / ChangeMe123!"))
