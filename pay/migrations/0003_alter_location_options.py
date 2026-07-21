from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("pay", "0002_central_vendor_platform")]

    operations = [
        migrations.AlterModelOptions(
            name="location",
            options={"ordering": ["position", "business__name", "name"]},
        ),
    ]
