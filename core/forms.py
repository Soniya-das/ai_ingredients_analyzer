from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Product, Ingredient

class RegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone = forms.CharField(max_length=15, required=True)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'phone', 'password1', 'password2']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                phone=self.cleaned_data['phone']
            )
        return user

class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)

class ForgotPasswordForm(forms.Form):
    email = forms.EmailField()

# class ResetPasswordForm(forms.Form):
#     new_password = forms.CharField(
#         label='New Password',
#         widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter new password'}),
#         min_length=6
#     )
#     confirm_password = forms.CharField(
#         label='Confirm Password',
#         widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm new password'})
#     )
    
#     def clean(self):
#         cleaned_data = super().clean()
#         new_password = cleaned_data.get('new_password')
#         confirm_password = cleaned_data.get('confirm_password')
        
#         if new_password and confirm_password:
#             if new_password != confirm_password:
#                 raise forms.ValidationError("Passwords do not match")
#         return cleaned_data


# In your forms.py, add this if you want to use Django forms

from django import forms
from django.core.exceptions import ValidationError
import re

class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(widget=forms.PasswordInput, required=True)
    confirm_password = forms.CharField(widget=forms.PasswordInput, required=True)
    
    def clean_new_password(self):
        password = self.cleaned_data.get('new_password', '')
        errors = []
        
        if len(password) < 6:
            errors.append('Password must be at least 6 characters long.')
        
        if not re.search(r'[a-z]', password):
            errors.append('Password must contain at least one lowercase letter.')
        
        if not re.search(r'[A-Z]', password):
            errors.append('Password must contain at least one uppercase letter.')
        
        if not re.search(r'[0-9]', password):
            errors.append('Password must contain at least one number.')
        
        if errors:
            raise ValidationError(' '.join(errors))
        
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if new_password and confirm_password and new_password != confirm_password:
            raise ValidationError('Passwords do not match.')
        
        return cleaned_data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone', 'date_of_birth', 'skin_type']

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'brand', 'category', 'description', 'price', 'image']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = ['name', 'category', 'description', 'side_effects', 'suitable_for', 'not_suitable_for']