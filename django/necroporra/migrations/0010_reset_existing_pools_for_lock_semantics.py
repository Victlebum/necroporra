from django.db import migrations


def delete_existing_pools(apps, schema_editor):
    Pool = apps.get_model('necroporra', 'Pool')
    Pool.objects.all().delete()


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('necroporra', '0009_remove_pool_picks_visibility_date_and_more'),
    ]

    operations = [
        migrations.RunPython(delete_existing_pools, noop_reverse),
    ]
