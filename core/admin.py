from django.contrib import admin
from .models import UserProfile, Ingredient, Product, ProductIngredient, AnalysisReport

admin.site.register(UserProfile)
admin.site.register(Ingredient)
admin.site.register(Product)
admin.site.register(ProductIngredient)
admin.site.register(AnalysisReport)