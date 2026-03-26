from django.core.management.base import BaseCommand
from django.utils import timezone

from necroporra.models import Pool


class Command(BaseCommand):
    help = 'Close pools whose close date has passed'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Updating pool open/closed state...'))

        now = timezone.now()
        pools_to_update = Pool.objects.filter(
            is_locked=False,
            lock_date__isnull=False,
            lock_date__lte=now,
        )

        count = 0
        for pool in pools_to_update:
            pool.is_locked = True
            pool.save(update_fields=['is_locked'])
            count += 1
            self.stdout.write(
                self.style.SUCCESS(f'✓ Pool "{pool.name}" ({pool.slug}) closed')
            )

        if count == 0:
            self.stdout.write(self.style.WARNING('No pools need state updates'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Updated closed state for {count} pool{"s" if count != 1 else ""}')
            )
