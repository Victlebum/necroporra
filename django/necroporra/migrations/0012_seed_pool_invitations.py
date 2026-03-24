from datetime import timedelta
import secrets
import string

from django.db import migrations
from django.utils import timezone


INVITE_EXPIRATION_DAYS = 14
TOKEN_LENGTH = 32


def _generate_unique_token(PoolInvitation):
    alphabet = string.ascii_letters + string.digits
    while True:
        token = ''.join(secrets.choice(alphabet) for _ in range(TOKEN_LENGTH))
        if not PoolInvitation.objects.filter(token=token).exists():
            return token


def seed_pool_invitations(apps, schema_editor):
    Pool = apps.get_model('necroporra', 'Pool')
    PoolInvitation = apps.get_model('necroporra', 'PoolInvitation')

    expiration = timezone.now() + timedelta(days=INVITE_EXPIRATION_DAYS)

    for pool in Pool.objects.all().iterator():
        has_active = PoolInvitation.objects.filter(pool=pool, is_active=True).exists()
        if has_active:
            continue

        PoolInvitation.objects.create(
            pool=pool,
            token=_generate_unique_token(PoolInvitation),
            expires_at=expiration,
            is_active=True,
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('necroporra', '0011_alter_pool_is_public_poolinvitation'),
    ]

    operations = [
        migrations.RunPython(seed_pool_invitations, noop_reverse),
    ]
