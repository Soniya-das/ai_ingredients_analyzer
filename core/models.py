from django.db import models
from django.contrib.auth.models import User
from datetime import datetime
from django.utils import timezone
from datetime import timedelta


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)
    date_of_birth = models.DateField(null=True, blank=True)
    skin_type = models.CharField(max_length=50, choices=[
        ('oily', 'Oily'), ('dry', 'Dry'), ('combination', 'Combination'), 
        ('normal', 'Normal'), ('sensitive', 'Sensitive')
    ], null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.user.username


class Ingredient(models.Model):
    CATEGORY_CHOICES = [
        ('safe', 'Safe ✅'),
        ('moderate', 'Moderate ⚠️'),
        ('harmful', 'Harmful ❌'),
    ]
    
    name = models.CharField(max_length=200, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    side_effects = models.TextField(blank=True)
    suitable_for = models.CharField(max_length=200, blank=True)
    not_suitable_for = models.CharField(max_length=200, blank=True)
    
    def __str__(self):
        return f"{self.name} - {self.category}"
    
    class Meta:
        ordering = ['name']


class Product(models.Model):
    CATEGORY_CHOICES = [
        ('skincare', 'Skincare'),
        ('haircare', 'Haircare'),
        ('food', 'Food'),
        ('supplements', 'Supplements'),
        ('baby', 'Baby Products'),
        ('cosmetics', 'Cosmetics'),
        ('medicines', 'Medicines'),
    ]
    
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', blank=True, null=True)  # ✅ Image field
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    
    # ✅ ADD THIS METHOD - For displaying category with emoji in templates
    def get_category_display(self):
        category_icons = {
            'skincare': '🧴 Skincare',
            'haircare': '💇 Haircare',
            'food': '🍎 Food',
            'supplements': '💊 Supplements',
            'baby': '👶 Baby Products',
            'cosmetics': '💄 Cosmetics',
            'medicines': '💉 Medicines',
        }
        return category_icons.get(self.category, self.category.title())


class ProductIngredient(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ingredients')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='products')
    concentration = models.CharField(max_length=50, blank=True)
    
    class Meta:
        unique_together = ['product', 'ingredient']
        


class AnalysisReport(models.Model):
    STATUS_CHOICES = [
        ('safe', 'Safe ✅'),
        ('moderate', 'Moderate ⚠️'),
        ('harmful', 'Harmful ❌'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=200)           # store product name
    ingredients_data = models.JSONField(default=list)         # store ingredient list
    safe_ingredients = models.IntegerField(default=0)
    moderate_ingredients = models.IntegerField(default=0)
    harmful_ingredients = models.IntegerField(default=0)
    overall_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='safe')
    recommendation = models.TextField()
    analyzed_at = models.DateTimeField(auto_now_add=True)
  


    # ADD THESE FIELDS:
    is_deleted_by_user = models.BooleanField(default=False)  # User soft delete
    is_deleted_by_admin = models.BooleanField(default=False)  # Admin permanent delete flag
    deleted_by_user_at = models.DateTimeField(null=True, blank=True)
    deleted_by_admin_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.product_name} - {self.analyzed_at}"
    
    class Meta:
        ordering = ['-analyzed_at']




class OTPSession(models.Model):
    email = models.EmailField()
    otp = models.CharField(max_length=6)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.email} - {self.otp} - Verified: {self.is_verified}"
    
    def is_expired(self):
        expiry_time = self.created_at + timedelta(minutes=10)
        return timezone.now() > expiry_time
    

# Add these new models to your existing models.py

class SkinTypeRecommendation(models.Model):
    """Stores ingredient recommendations for different skin types"""
    SKIN_TYPES = [
        ('oily', 'Oily Skin'),
        ('dry', 'Dry Skin'),
        ('combination', 'Combination Skin'),
        ('normal', 'Normal Skin'),
        ('sensitive', 'Sensitive Skin'),
    ]
    
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='skin_recommendations')
    skin_type = models.CharField(max_length=20, choices=SKIN_TYPES)
    suitability_score = models.IntegerField(default=50, help_text="0-100 score")
    recommendation_text = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['ingredient', 'skin_type']
    
    def __str__(self):
        return f"{self.ingredient.name} - {self.skin_type}: {self.suitability_score}"


class ScientificApproval(models.Model):
    """Tracks scientific approvals for ingredients"""
    APPROVAL_LEVELS = [
        ('fda', 'FDA Approved'),
        ('eu', 'EU Approved'),
        ('dermatologist', 'Dermatologist Recommended'),
        ('clinical', 'Clinically Proven'),
        ('research', 'Peer-Reviewed Research'),
        ('pending', 'Pending Approval'),
    ]
    
    ingredient = models.OneToOneField(Ingredient, on_delete=models.CASCADE, related_name='scientific_approval')
    approval_level = models.CharField(max_length=50, choices=APPROVAL_LEVELS, default='pending')
    approval_number = models.CharField(max_length=100, blank=True)
    approval_date = models.DateField(null=True, blank=True)
    research_papers = models.TextField(blank=True, help_text="Comma-separated research paper links or citations")
    clinical_studies = models.TextField(blank=True, help_text="Clinical study references")
    certifying_body = models.CharField(max_length=200, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.ingredient.name} - {self.get_approval_level_display()}"
    
    @property
    def is_active(self):
        if self.expiry_date:
            return timezone.now().date() <= self.expiry_date
        return True


class DermatologistSuggestion(models.Model):
    """Stores dermatologist suggestions and warnings"""
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='dermatologist_suggestions')
    suggestion_type = models.CharField(max_length=50, choices=[
        ('recommended', 'Highly Recommended'),
        ('caution', 'Use with Caution'),
        ('avoid', 'Avoid'),
        ('consult', 'Consult Dermatologist'),
    ])
    suggestion_text = models.TextField()
    dermatologist_name = models.CharField(max_length=200, blank=True)
    credentials = models.CharField(max_length=200, blank=True)
    reference_link = models.URLField(blank=True)
    
    def __str__(self):
        return f"{self.ingredient.name} - {self.suggestion_type}"


class SkinAnalysisReport(models.Model):
    """Enhanced skincare analysis report with skin type recommendations"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=200)
    user_skin_type = models.CharField(max_length=20, choices=SkinTypeRecommendation.SKIN_TYPES, null=True, blank=True)
    ingredients_analyzed = models.JSONField(default=list)
    
    # Overall scores
    overall_score = models.IntegerField(default=0, help_text="0-100 overall product score")
    skin_compatibility_score = models.IntegerField(default=0, help_text="0-100 compatibility with user's skin")
    safety_score = models.IntegerField(default=0)
    efficacy_score = models.IntegerField(default=0)
    
    # Counts
    safe_count = models.IntegerField(default=0)
    moderate_count = models.IntegerField(default=0)
    harmful_count = models.IntegerField(default=0)
    scientifically_approved_count = models.IntegerField(default=0)
    dermatologist_recommended_count = models.IntegerField(default=0)
    
    # Recommendations
    overall_verdict = models.CharField(max_length=50, choices=[
        ('excellent', 'Excellent Choice 🌟'),
        ('good', 'Good Choice ✅'),
        ('moderate', 'Use with Caution ⚠️'),
        ('avoid', 'Avoid ❌'),
    ], default='moderate')
    
    recommendation_summary = models.TextField()
    skin_specific_advice = models.TextField(blank=True)
    alternatives_suggested = models.JSONField(default=list, blank=True)
    
    analyzed_at = models.DateTimeField(auto_now_add=True)
    is_deleted_by_user = models.BooleanField(default=False)
    
    # ADD THIS FIELD:
    is_deleted_by_admin = models.BooleanField(default=False)  # Admin permanent delete flag
    
    class Meta:
        ordering = ['-analyzed_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.product_name} - Score: {self.overall_score}"


class UserSkinProfile(models.Model):
    """Enhanced user skin profile for personalized recommendations"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    skin_type = models.CharField(max_length=20, choices=SkinTypeRecommendation.SKIN_TYPES, default='normal')
    skin_concerns = models.JSONField(default=list, blank=True, help_text="e.g., ['acne', 'aging', 'dryness']")
    allergies = models.JSONField(default=list, blank=True)
    current_routine = models.JSONField(default=list, blank=True)
    preferred_textures = models.JSONField(default=list, blank=True)
    budget_range = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Skin Profile"
    



class RecentActivity(models.Model):
    ACTIVITY_TYPES = [
        ('user', 'User Activity'),
        ('product', 'Product Activity'),
        ('report', 'Report Activity'),
        ('ingredient', 'Ingredient Activity'),
        ('analysis', 'Analysis Activity'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.activity_type} - {self.description[:50]}"
