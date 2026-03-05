from django.core.management.base import BaseCommand
from datetime import datetime
import requests

from necroporra.models import (
    Celebrity, Pool, PoolCelebrity, Prediction,
    score_pool_celebrity, unscore_pool_celebrity,
)
from necroporra import wikidata_utils
from django.utils import timezone


class Command(BaseCommand):
    help = 'Sync celebrity deaths from Wikidata and update pool scoring'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Wikidata sync...'))

        # Get all pools (both active and ended to update scoring)
        pools = Pool.objects.all().prefetch_related('celebrities__celebrity')
        
        if not pools.exists():
            self.stdout.write(self.style.WARNING('No pools found'))
            return

        for pool in pools:
            self.sync_pool_deaths(pool)
            
            # Mark predictions as incorrect for expired pools
            if not pool.is_pool_active():
                self.mark_expired_predictions(pool)

        self.stdout.write(self.style.SUCCESS('Wikidata sync completed'))

    def sync_pool_deaths(self, pool):
        """Sync deaths for celebrities in a specific pool."""
        pool_celebrities = pool.celebrities.filter(is_death_recorded=False).select_related('celebrity')

        for pool_celebrity in pool_celebrities:
            celebrity = pool_celebrity.celebrity

            if not celebrity.death_date:
                # Query Wikidata for death information
                death_date = self.query_wikidata_for_death(celebrity)

                if death_date:
                    # If there was a manual death date, undo its scoring first —
                    # the Wikidata (natural) death overrules the manual mark.
                    if pool_celebrity.manual_death_date:
                        unscore_pool_celebrity(pool_celebrity)
                        pool_celebrity.manual_death_date = None

                    celebrity.death_date = death_date
                    celebrity.save()

                    pool_celebrity.is_death_recorded = True
                    pool_celebrity.save()

                    score_pool_celebrity(pool_celebrity)

                    self.stdout.write(
                        self.style.SUCCESS(f'✓ {celebrity.name} death recorded: {death_date}')
                    )
            else:
                # Celebrity already has a global death date — just mark as recorded and score.
                pool_celebrity.is_death_recorded = True
                pool_celebrity.save()
                score_pool_celebrity(pool_celebrity)

    def query_wikidata_for_death(self, celebrity):
        """Query Wikidata API for a celebrity's death date."""
        try:
            # Search by name if no wikidata_id
            if not celebrity.wikidata_id:
                # Search for celebrity using wikidata_utils
                search_url = "https://www.wikidata.org/w/api.php"
                search_params = {
                    'action': 'wbsearchentities',
                    'search': celebrity.name,
                    'language': 'en',
                    'format': 'json'
                }
                
                headers = {
                    'User-Agent': 'Necroporra/1.0 (Celebrity Death Pool App; Educational Project)'
                }
                
                response = requests.get(search_url, params=search_params, headers=headers, timeout=5)
                if response.status_code != 200:
                    return None
                
                data = response.json()
                if not data.get('search'):
                    return None
                
                entity_id = data['search'][0]['id']
                celebrity.wikidata_id = entity_id
                celebrity.save()

            # Use wikidata_utils to get full entity data
            entity_data = wikidata_utils.get_wikidata_entity(celebrity.wikidata_id)
            
            if entity_data and entity_data.get('death_date'):
                # Parse the ISO date string to date object
                death_date_str = entity_data['death_date']
                date_obj = datetime.fromisoformat(death_date_str)
                return date_obj.date()

            return None

        except (requests.RequestException, KeyError, IndexError, ValueError) as e:
            self.stdout.write(
                self.style.WARNING(f'Error querying Wikidata for {celebrity.name}: {str(e)}')
            )
            return None

    def mark_expired_predictions(self, pool):
        """Mark predictions as incorrect for expired pools where the celebrity has no death date in pool context."""
        # Build a per-celebrity effective_death_date lookup for this pool
        pc_lookup = {
            pc.celebrity_id: pc.effective_death_date
            for pc in pool.celebrities.select_related('celebrity').all()
        }

        expired_predictions = Prediction.objects.filter(
            pool=pool,
            is_correct__isnull=True,
        ).select_related('celebrity')

        for prediction in expired_predictions:
            effective_death = pc_lookup.get(prediction.celebrity_id)
            if not effective_death:
                prediction.is_correct = False
                prediction.points_earned = 0
                prediction.save()

                self.stdout.write(
                    self.style.WARNING(
                        f"Pool {pool.slug}: {prediction.user.username}'s prediction "
                        f"for {prediction.celebrity.name} expired (still alive)"
                    )
                )
