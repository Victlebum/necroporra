from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('necroporra', '0004_remove_timeframe_years'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pool',
            name='scoring_mode',
            field=models.CharField(
                choices=[
                    ('simple', 'Simple - 1 point per correct prediction'),
                    ('distributed', 'Distributed - Allocate 10 points across predictions'),
                ],
                default='simple',
                help_text='How points are calculated for correct predictions',
                max_length=20,
            ),
        ),
    ]
