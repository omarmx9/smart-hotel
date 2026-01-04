# Generated migration for Authentik OIDC integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),  # Adjust this to your latest migration
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='oidc_sub',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        # Remove PasswordResetToken model as it's no longer needed with Authentik
        migrations.DeleteModel(
            name='PasswordResetToken',
        ),
    ]
