# core/management/commands/populate_ingredients.py

import logging
from django.core.management.base import BaseCommand
from django.db import IntegrityError
from core.models import Ingredient
from core.utils import StaticIngredientAnalyzer

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populate Ingredient table from static sets in utils.py'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Only show what would be added, without saving to database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Collect all ingredients from all categories with priority
        # Priority: harmful (3) > moderate (2) > safe (1)
        ingredient_priority = {}

        # Categories and their sets
        categories = [
            ('skincare', StaticIngredientAnalyzer.SKINCARE_SAFE,
                        StaticIngredientAnalyzer.SKINCARE_MODERATE,
                        StaticIngredientAnalyzer.SKINCARE_HARMFUL),
            ('haircare', StaticIngredientAnalyzer.HAIRCARE_SAFE,
                         StaticIngredientAnalyzer.HAIRCARE_MODERATE,
                         StaticIngredientAnalyzer.HAIRCARE_HARMFUL),
            ('baby', StaticIngredientAnalyzer.BABY_SAFE,
                     StaticIngredientAnalyzer.BABY_MODERATE,
                     StaticIngredientAnalyzer.BABY_HARMFUL),
            ('cosmetics', StaticIngredientAnalyzer.COSMETICS_SAFE,
                          StaticIngredientAnalyzer.COSMETICS_MODERATE,
                          StaticIngredientAnalyzer.COSMETICS_HARMFUL),
            ('food', StaticIngredientAnalyzer.FOOD_SAFE,
                     StaticIngredientAnalyzer.FOOD_MODERATE,
                     StaticIngredientAnalyzer.FOOD_HARMFUL),
            ('supplements', StaticIngredientAnalyzer.SUPPLEMENTS_SAFE,
                            StaticIngredientAnalyzer.SUPPLEMENTS_MODERATE,
                            StaticIngredientAnalyzer.SUPPLEMENTS_HARMFUL),
            ('medicines', StaticIngredientAnalyzer.MEDICINES_SAFE,
                          StaticIngredientAnalyzer.MEDICINES_MODERATE,
                          StaticIngredientAnalyzer.MEDICINES_HARMFUL),
        ]

        for cat_name, safe_set, mod_set, harm_set in categories:
            # Harmful has highest priority (3)
            for ing in harm_set:
                key = ing.lower().strip()
                if key not in ingredient_priority or ingredient_priority[key][0] < 3:
                    ingredient_priority[key] = (3, ing, 'harmful')
            # Moderate (priority 2)
            for ing in mod_set:
                key = ing.lower().strip()
                if key not in ingredient_priority or ingredient_priority[key][0] < 2:
                    ingredient_priority[key] = (2, ing, 'moderate')
            # Safe (priority 1)
            for ing in safe_set:
                key = ing.lower().strip()
                if key not in ingredient_priority:
                    ingredient_priority[key] = (1, ing, 'safe')

        # Add BANNED_INGREDIENTS, MEDICAL_RISK_INGREDIENTS, FRAGRANCE_ALLERGENS
        banned = StaticIngredientAnalyzer.BANNED_INGREDIENTS
        med_risk = StaticIngredientAnalyzer.MEDICAL_RISK_INGREDIENTS
        fragrance = StaticIngredientAnalyzer.FRAGRANCE_ALLERGENS

        for ing in banned | med_risk:
            key = ing.lower().strip()
            if key not in ingredient_priority or ingredient_priority[key][0] < 3:
                ingredient_priority[key] = (3, ing, 'harmful')
        for ing in fragrance:
            key = ing.lower().strip()
            if key not in ingredient_priority or ingredient_priority[key][0] < 2:
                ingredient_priority[key] = (2, ing, 'moderate')

        self.stdout.write(f"Total unique ingredients to process: {len(ingredient_priority)}")

        if dry_run:
            self.stdout.write("DRY RUN – no changes will be made to database.")
            for i, (_, (_, name, cat)) in enumerate(list(ingredient_priority.items())[:10]):
                self.stdout.write(f"  {name} -> {cat}")
            self.stdout.write(f"... and {len(ingredient_priority)-10} more.")
            return

        # Insert/update in database
        created = 0
        updated = 0
        skipped = 0

        for key, (_, name, category) in ingredient_priority.items():
            try:
                defaults = {
                    'category': category,
                    'description': f"{name} is a {category} ingredient.",
                    'suitable_for': 'General use',
                    'side_effects': '',
                    'not_suitable_for': '',
                }
                obj, created_flag = Ingredient.objects.update_or_create(
                    name=name,
                    defaults=defaults
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1
            except IntegrityError as e:
                self.stdout.write(self.style.WARNING(f"Skipped {name}: {e}"))
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created: {created}, Updated: {updated}, Skipped: {skipped}"
        ))