from django.core.management.base import BaseCommand
from django.utils import timezone

from necroporra.models import Pool


class Command(BaseCommand):
    help = 'Update pool pick visibility based on visibility dates'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Updating pool visibility...'))

        # Find pools that should become visible now
        now = timezone.now()
        pools_to_update = Pool.objects.filter(
            picks_visible=False,
            picks_visibility_date__isnull=False,
            picks_visibility_date__lte=now
        )

        count = 0
        for pool in pools_to_update:
            pool.picks_visible = True
            pool.save()
            count += 1
            self.stdout.write(
                self.style.SUCCESS(f'✓ Pool "{pool.name}" ({pool.slug}) - picks now visible')
            )

        if count == 0:
            self.stdout.write(self.style.WARNING('No pools need visibility updates'))
        else:
            self.stdout.write(
                self.style.SUCCESS(f'Updated visibility for {count} pool{"s" if count != 1 else ""}')
            )
