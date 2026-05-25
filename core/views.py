# core/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.db.models import Q, Avg, Count
from django.db import IntegrityError
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods
from django.utils import timezone
from django.urls import reverse
from itertools import chain
import random
import os
import json
import logging
from django.core.paginator import Paginator

from .forms import *
from .models import *
from .utils import StaticIngredientAnalyzer
from .utils_ai import RealAIAnalyzer

logger = logging.getLogger(__name__)

# ------------------- OTP & AUTH -------------------
def generate_otp():
    return str(random.randint(100000, 999999))

def index(request):
    return render(request, 'index.html')

def user_register(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            try:
                email = form.cleaned_data.get('email')
                if User.objects.filter(email=email).exists():
                    messages.error(request, 'Email already registered! Please use a different email or login.')
                    return render(request, 'register.html', {'form': form})
                user = form.save()
                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'phone': form.cleaned_data.get('phone', ''),
                        'date_of_birth': None,
                        'skin_type': 'normal'
                    }
                )
                login(request, user)
                messages.success(request, 'Registration successful! Welcome to AI Smart Care Analyzer!')
                return redirect('dashboard')
            except IntegrityError:
                messages.error(request, 'Registration failed. Please try again.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = RegistrationForm()
    return render(request, 'register.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, f'Welcome back, {username}! 👋')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password. Please try again.')
    return render(request, 'login.html')

def forgot_password(request):
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                users = User.objects.filter(email=email)
                user_count = users.count()
                if user_count == 0:
                    messages.error(request, 'No account found with this email address.')
                    return render(request, 'forgot-password.html', {'form': form})
                user = users.order_by('-date_joined').first()
                if user_count > 1:
                    messages.warning(request, f'Multiple accounts found with this email. Using the most recent account (Username: {user.username}).')
                otp = generate_otp()
                OTPSession.objects.filter(email=email).delete()
                OTPSession.objects.create(email=email, otp=otp)
                try:
                    send_mail(
                        'Password Reset OTP - AI Smart Care Analyzer',
                        f'Dear {user.username},\n\nYour OTP for password reset is: {otp}\n\nThis OTP is valid for 10 minutes.\n\nIf you did not request this, please ignore this email.',
                        settings.EMAIL_HOST_USER,
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, 'OTP sent to your email successfully!')
                except Exception as e:
                    print(f"\n{'='*50}")
                    print(f"🔐 OTP for {email}: {otp}")
                    print(f"Username: {user.username}")
                    print(f"{'='*50}\n")
                    messages.warning(request, f'Email sending failed. Use OTP: {otp}')
                request.session['reset_email'] = email
                return redirect('verify-otp')
            except Exception as e:
                messages.error(request, f'An error occurred: {str(e)}')
    else:
        form = ForgotPasswordForm()
    return render(request, 'forgot-password.html', {'form': form})

def verify_otp(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('forgot-password')
    if request.method == 'POST':
        otp = request.POST.get('otp')
        otp_session = OTPSession.objects.filter(email=email, otp=otp, is_verified=False).first()
        if otp_session:
            from datetime import timedelta
            expiry_time = otp_session.created_at + timedelta(minutes=10)
            if timezone.now() > expiry_time:
                otp_session.delete()
                messages.error(request, 'OTP has expired. Please request a new one.')
                return redirect('forgot-password')
            otp_session.is_verified = True
            otp_session.save()
            messages.success(request, 'OTP verified successfully!')
            return redirect('reset-password')
        else:
            messages.error(request, 'Invalid OTP. Please try again.')
    return render(request, 'otp-verify.html')

def reset_password(request):
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Session expired. Please try again.')
        return redirect('forgot-password')
    
    otp_verified = OTPSession.objects.filter(email=email, is_verified=True).exists()
    if not otp_verified:
        messages.error(request, 'Please verify OTP first.')
        return redirect('verify-otp')
    
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()
        
        errors = []
        if new_password != confirm_password:
            errors.append('Passwords do not match.')
        if len(new_password) < 6:
            errors.append('Password must be at least 6 characters long.')
        if not any(c.islower() for c in new_password):
            errors.append('Password must contain at least one lowercase letter.')
        if not any(c.isupper() for c in new_password):
            errors.append('Password must contain at least one uppercase letter.')
        if not any(c.isdigit() for c in new_password):
            errors.append('Password must contain at least one number.')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?/' for c in new_password):
            errors.append('Password must contain at least one symbol.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'reset-password.html')
        
        try:
            users = User.objects.filter(email=email)
            if users.count() == 0:
                messages.error(request, 'User not found.')
                return redirect('forgot-password')
            user = users.order_by('-date_joined').first()
            user.set_password(new_password)
            user.save()
            OTPSession.objects.filter(email=email).delete()
            if 'reset_email' in request.session:
                del request.session['reset_email']
            messages.success(request, '✅ Password reset successful! Please login with your new password.')
            return redirect('login')
        except Exception as e:
            messages.error(request, f'Error resetting password: {str(e)}')
            return render(request, 'reset-password.html')
    return render(request, 'reset-password.html')

# ------------------- DASHBOARD & PROFILE -------------------
@login_required
def dashboard(request):
    user_reports = AnalysisReport.objects.filter(user=request.user, is_deleted_by_user=False).order_by('-analyzed_at')[:5]
    total_reports = AnalysisReport.objects.filter(user=request.user, is_deleted_by_user=False).count()
    total_products = Product.objects.count()
    
    total_safe_ingredients = 0
    total_all_ingredients = 0
    all_reports = AnalysisReport.objects.filter(user=request.user, is_deleted_by_user=False)
    for report in all_reports:
        for ing in report.ingredients_data:
            total_all_ingredients += 1
            if ing.get('status', '').strip().lower() == 'safe':
                total_safe_ingredients += 1
    safe_percentage = int((total_safe_ingredients / total_all_ingredients) * 100) if total_all_ingredients > 0 else 0
    
    context = {
        'reports': user_reports,
        'total_reports': total_reports,
        'total_products': total_products,
        'welcome_name': request.user.get_full_name() or request.user.username,
        'safe_percentage': safe_percentage,
    }
    return render(request, 'dashboard.html', context)

@login_required
def profile(request):
    profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={'phone': '', 'date_of_birth': None, 'skin_type': 'normal'}
    )
    if created:
        messages.info(request, 'Please complete your profile information.')
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully! ✨')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileForm(instance=profile)
    context = {'form': form, 'profile': profile, 'user': request.user}
    return render(request, 'profile.html', context)

# ------------------- PRODUCT SEARCH -------------------
@login_required
def search_product(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    products = Product.objects.all()
    categories = [
        ('skincare', '🧴 Skincare'), ('haircare', '💇 Haircare'), ('food', '🍎 Food'),
        ('supplements', '💊 Supplements'), ('baby', '👶 Baby Products'),
        ('cosmetics', '💄 Cosmetics'), ('medicines', '💉 Medicines'),
    ]
    if query:
        exact_matches = products.filter(Q(name__iexact=query) | Q(brand__iexact=query))
        partial_matches = products.filter(
            Q(name__icontains=query) | Q(brand__icontains=query) | Q(description__icontains=query)
        ).exclude(id__in=exact_matches)
        products = list(chain(exact_matches, partial_matches))
    else:
        products = products.order_by('-created_at')
    if category:
        if isinstance(products, list):
            products = [p for p in products if p.category == category]
        else:
            products = products.filter(category=category)
    context = {'products': products, 'query': query, 'category': category, 'categories': categories}
    return render(request, 'search-product.html', context)

@login_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product_ingredients = ProductIngredient.objects.filter(product=product).select_related('ingredient')
    safe_count = product_ingredients.filter(ingredient__category='safe').count()
    moderate_count = product_ingredients.filter(ingredient__category='moderate').count()
    harmful_count = product_ingredients.filter(ingredient__category='harmful').count()
    context = {
        'product': product,
        'product_ingredients': product_ingredients,
        'safe_count': safe_count,
        'moderate_count': moderate_count,
        'harmful_count': harmful_count,
    }
    return render(request, 'product-detail.html', context)

# ------------------- INGREDIENT ANALYZER (HYBRID AI + STATIC) -------------------
@login_required
def analyzer(request):
    if request.method == 'POST':
        product_name = request.POST.get('product_name', '').strip()
        ingredients_text = request.POST.get('ingredients', '').strip()
        product_category = request.POST.get('category', 'skincare')

        if not product_name or not ingredients_text:
            messages.error(request, 'Please provide both product name and ingredients.')
            return redirect('analyzer')

        static_result = StaticIngredientAnalyzer.analyze_ingredients(ingredients_text, product_category)
        result = static_result
        
        unknown_count = static_result.get('unknown_count', 0)
        total_count = static_result.get('total_ingredients', 0)
        use_ai = (unknown_count > 0 and (unknown_count / total_count) > 0.5) if total_count > 0 else False
        
        if use_ai:
            try:
                ai_analyzer = RealAIAnalyzer()
                ai_result = ai_analyzer.analyze_ingredients(ingredients_text, product_category)
                result = RealAIAnalyzer.merge_static_and_ai(static_result, ai_result)
            except Exception as e:
                logger.error(f"AI analysis failed (fallback to static): {e}")
                result = static_result

        report = AnalysisReport.objects.create(
            user=request.user,
            product_name=product_name,
            ingredients_data=result.get('ingredients', []),
            safe_ingredients=result.get('safe_count', 0),
            moderate_ingredients=result.get('moderate_count', 0),
            harmful_ingredients=result.get('harmful_count', 0),
            overall_status=result.get('overall_status', 'safe'),
            recommendation=result.get('recommendation', '')
        )

        messages.success(request, f'✅ Analysis complete for "{product_name}"!')
        return render(request, 'analyzer-result.html', {
            'result': result,
            'product_name': product_name,
            'report_id': report.id,
            'category': product_category
        })
    return render(request, 'analyzer.html')

# ------------------- REPORTS -------------------
@login_required
def report(request, report_id):
    if request.user.is_superuser:
        report_obj = get_object_or_404(AnalysisReport, id=report_id)
    else:
        report_obj = get_object_or_404(AnalysisReport, id=report_id, user=request.user)

    ingredients = report_obj.ingredients_data
    fixed = False
    for ing in ingredients:
        raw = ing.get('status')
        if raw is None:
            normalized = 'unknown'
            fixed = True
        else:
            normalized = str(raw).strip().lower()
            if normalized not in ('safe', 'moderate', 'harmful'):
                normalized = 'unknown'
                fixed = True
            elif normalized != raw:
                fixed = True
        ing['status'] = normalized

    if fixed:
        report_obj.ingredients_data = ingredients
        report_obj.save()

    safe_ingredients = [ing for ing in ingredients if ing.get('status') == 'safe']
    moderate_ingredients = [ing for ing in ingredients if ing.get('status') == 'moderate']
    harmful_ingredients = [ing for ing in ingredients if ing.get('status') == 'harmful']

    context = {
        'report': report_obj,
        'product_name': report_obj.product_name,
        'safe_ingredients': safe_ingredients,
        'moderate_ingredients': moderate_ingredients,
        'harmful_ingredients': harmful_ingredients,
        'total_ingredients': len(ingredients),
    }
    return render(request, 'report.html', context)

# This is the FINAL (cleaned) report_history - includes both filters
@login_required
def report_history(request):
    reports = AnalysisReport.objects.filter(
        user=request.user,
        is_deleted_by_user=False,
        is_deleted_by_admin=False
    ).order_by('-analyzed_at')
    
    safe_reports_count = 0
    moderate_reports_count = 0
    harmful_reports_count = 0
    total_safe_ings = 0
    total_moderate_ings = 0
    total_harmful_ings = 0
    updated_reports = []
    
    for report in reports:
        ingredients = report.ingredients_data
        safe_cnt = moderate_cnt = harmful_cnt = 0
        for ing in ingredients:
            status = ing.get('status', '').strip().lower()
            if status == 'safe':
                safe_cnt += 1
            elif status == 'moderate':
                moderate_cnt += 1
            elif status == 'harmful':
                harmful_cnt += 1
        total_safe_ings += safe_cnt
        total_moderate_ings += moderate_cnt
        total_harmful_ings += harmful_cnt
        
        if harmful_cnt > 0:
            harmful_reports_count += 1
            report_category = 'harmful'
        elif safe_cnt > moderate_cnt:
            safe_reports_count += 1
            report_category = 'safe'
        else:
            moderate_reports_count += 1
            report_category = 'moderate'
        
        report_dict = {
            'id': report.id,
            'product_name': report.product_name,
            'analyzed_at': report.analyzed_at,
            'overall_status': report_category,
            'recommendation': report.recommendation,
            'safe_ingredients': safe_cnt,
            'moderate_ingredients': moderate_cnt,
            'harmful_ingredients': harmful_cnt,
        }
        updated_reports.append(report_dict)
        
        if (report.safe_ingredients != safe_cnt or 
            report.moderate_ingredients != moderate_cnt or 
            report.harmful_ingredients != harmful_cnt or
            report.overall_status != report_category):
            report.safe_ingredients = safe_cnt
            report.moderate_ingredients = moderate_cnt
            report.harmful_ingredients = harmful_cnt
            report.overall_status = report_category
            report.save()

    context = {
        'reports': updated_reports,
        'total_analyzed': reports.count(),
        'safe_reports': safe_reports_count,
        'moderate_reports': moderate_reports_count,
        'harmful_reports': harmful_reports_count,
        'total_safe_ingredients': total_safe_ings,
        'total_moderate_ingredients': total_moderate_ings,
        'total_harmful_ingredients': total_harmful_ings,
    }
    return render(request, 'report-history.html', context)

# This is the FINAL delete_report (with AJAX support)
@login_required
def delete_report(request, report_id):
    if request.user.is_superuser:
        report_obj = get_object_or_404(AnalysisReport, id=report_id)
        product_name = report_obj.product_name
        report_obj.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': f'Report for "{product_name}" deleted permanently!'})
        messages.success(request, f'Report for "{product_name}" deleted permanently from system!')
        return redirect('view-reports')
    else:
        report_obj = get_object_or_404(AnalysisReport, id=report_id, user=request.user)
        product_name = report_obj.product_name
        report_obj.is_deleted_by_user = True
        report_obj.deleted_by_user_at = timezone.now()
        report_obj.save()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': f'Report for "{product_name}" removed from your history!'})
        messages.success(request, f'✅ Report for "{product_name}" removed from your history. (Admin can still view it)')
        return redirect('report-history')

@login_required
def filter_by_status(request, status):
    user_reports = AnalysisReport.objects.filter(user=request.user, is_deleted_by_user=False).order_by('-analyzed_at')
    filtered_products = []
    for report_obj in user_reports:
        ingredients = report_obj.ingredients_data
        if status == 'safe':
            filtered_ings = [ing for ing in ingredients if ing.get('status', '').strip().lower() == 'safe']
        elif status == 'moderate':
            filtered_ings = [ing for ing in ingredients if ing.get('status', '').strip().lower() == 'moderate']
        elif status == 'harmful':
            filtered_ings = [ing for ing in ingredients if ing.get('status', '').strip().lower() == 'harmful']
        else:
            continue
        if filtered_ings:
            filtered_products.append({
                'product_name': report_obj.product_name,
                'ingredient_count': len(filtered_ings),
                'ingredients': filtered_ings,
                'report_date': report_obj.analyzed_at,
                'report_id': report_obj.id,
                'overall_status': report_obj.overall_status
            })
    status_info = {
        'safe': {'name': 'Safe Ingredients', 'icon': '✅', 'color': '#48bb78'},
        'moderate': {'name': 'Moderate Ingredients', 'icon': '⚠️', 'color': '#ed8936'},
        'harmful': {'name': 'Harmful Ingredients', 'icon': '❌', 'color': '#f56565'}
    }
    context = {
        'products': filtered_products,
        'status': status,
        'status_info': status_info.get(status, {'name': status, 'icon': '📊', 'color': '#667eea'}),
        'total_count': len(filtered_products)
    }
    return render(request, 'filtered-products.html', context)

@login_required
def ingredient_detail_list(request, status):
    user_reports = AnalysisReport.objects.filter(user=request.user)
    ingredients_set = set()
    for report_obj in user_reports:
        for ing in report_obj.ingredients_data:
            if ing.get('status', '').strip().lower() == status:
                ingredients_set.add(ing.get('name'))
    ingredients = [{'name': name, 'status': status} for name in sorted(ingredients_set)]
    status_info = {
        'safe': {'name': 'Safe Ingredients', 'icon': '✅', 'color': '#48bb78'},
        'moderate': {'name': 'Moderate Ingredients', 'icon': '⚠️', 'color': '#ed8936'},
        'harmful': {'name': 'Harmful Ingredients', 'icon': '❌', 'color': '#f56565'}
    }
    return render(request, 'ingredient-list.html', {
        'ingredients': ingredients,
        'status': status,
        'status_info': status_info.get(status, {}),
        'total_count': len(ingredients)
    })

# ------------------- ADMIN VIEWS -------------------
@login_required       
def admin_dashboard(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    
    total_users = User.objects.filter(is_superuser=False).count()
    total_products = Product.objects.count()
    total_reports = AnalysisReport.objects.filter(is_deleted_by_admin=False).count()
    total_ingredients = Ingredient.objects.count()
    total_skin_reports = SkinAnalysisReport.objects.filter(is_deleted_by_admin=False).count()
    
    recent_users = User.objects.filter(is_superuser=False).order_by('-date_joined')[:5]
    recent_reports = AnalysisReport.objects.filter(is_deleted_by_admin=False).order_by('-analyzed_at')[:5]
    recent_skin_reports = SkinAnalysisReport.objects.filter(is_deleted_by_admin=False).order_by('-analyzed_at')[:5]
    
    context = {
        'total_users': total_users,
        'total_products': total_products,
        'total_reports': total_reports,
        'total_ingredients': total_ingredients,
        'total_skin_reports': total_skin_reports,
        'recent_users': recent_users,
        'recent_reports': recent_reports,
        'recent_skin_reports': recent_skin_reports,
    }
    return render(request, 'admin/admin-dashboard.html', context)

# FINAL admin_skin_reports (robust version)
@login_required
def admin_skin_reports(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    
    try:
        reports = SkinAnalysisReport.objects.select_related('user').filter(is_deleted_by_admin=False).order_by('-analyzed_at')
    except:
        reports = SkinAnalysisReport.objects.select_related('user').all().order_by('-analyzed_at')
    
    report_data = []
    for report in reports:
        report_data.append({
            'report': report,
            'username_display': report.user.username,
            'is_deleted_by_user': getattr(report, 'is_deleted_by_user', False),
            'verdict_class': {
                'excellent': 'success',
                'good': 'info',
                'moderate': 'warning',
                'avoid': 'danger'
            }.get(report.overall_verdict, 'secondary')
        })
    
    total_reports = reports.count()
    avg_score = reports.aggregate(Avg('overall_score'))['overall_score__avg'] or 0
    
    context = {
        'reports': report_data,
        'total_reports': total_reports,
        'avg_score': round(avg_score, 1),
        'excellent_count': reports.filter(overall_verdict='excellent').count(),
        'good_count': reports.filter(overall_verdict='good').count(),
        'moderate_count': reports.filter(overall_verdict='moderate').count(),
        'avoid_count': reports.filter(overall_verdict='avoid').count(),
    }
    return render(request, 'admin/admin-skin-reports.html', context)

@login_required
def admin_skin_delete_report_permanent(request, report_id):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    report_obj = get_object_or_404(SkinAnalysisReport, id=report_id)
    product_name = report_obj.product_name
    username = report_obj.user.username
    RecentActivity.objects.create(
        user=request.user,
        activity_type='report',
        description=f"Admin permanently deleted skin report '{product_name}' for user {username}",
        status='deleted'
    )
    report_obj.delete()
    messages.success(request, f'🗑️ Skin report for "{product_name}" (User: {username}) permanently deleted!')
    return redirect('admin-skin-reports')

@login_required
def admin_skin_restore_report(request, report_id):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    report_obj = get_object_or_404(SkinAnalysisReport, id=report_id)
    product_name = report_obj.product_name
    username = report_obj.user.username
    report_obj.is_deleted_by_user = False
    report_obj.save()
    RecentActivity.objects.create(
        user=request.user,
        activity_type='report',
        description=f"Admin restored skin report '{product_name}' for user {username}",
        status='restored'
    )
    messages.success(request, f'🔄 Skin report for "{product_name}" (User: {username}) restored! User can now see it again.')
    return redirect('admin-skin-reports')

@login_required
def admin_delete_report_permanent(request, report_id):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    report_obj = get_object_or_404(AnalysisReport, id=report_id)
    product_name = report_obj.product_name
    username = report_obj.user.username
    RecentActivity.objects.create(
        user=request.user,
        activity_type='report',
        description=f"Admin permanently deleted product report '{product_name}' for user {username}",
        status='deleted'
    )
    report_obj.delete()
    messages.success(request, f'🗑️ Report for "{product_name}" (User: {username}) permanently deleted!')
    return redirect('view-reports')

@login_required
def admin_restore_report(request, report_id):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    report_obj = get_object_or_404(AnalysisReport, id=report_id)
    product_name = report_obj.product_name
    username = report_obj.user.username
    report_obj.is_deleted_by_user = False
    report_obj.save()
    RecentActivity.objects.create(
        user=request.user,
        activity_type='report',
        description=f"Admin restored product report '{product_name}' for user {username}",
        status='restored'
    )
    messages.success(request, f'🔄 Report for "{product_name}" (User: {username}) restored!')
    return redirect('view-reports')

# FINAL skin_report_delete (user soft delete)
@login_required
def skin_report_delete(request, report_id):
    report = get_object_or_404(SkinAnalysisReport, id=report_id, user=request.user)
    product_name = report.product_name
    report.is_deleted_by_user = True
    report.save()
    messages.success(request, f'✅ Skin report for "{product_name}" removed from your history. (Admin can still view it)')
    return redirect('skin-report-history')

# FINAL skin_report_history (user history with both filters)
@login_required
def skin_report_history(request):
    reports = SkinAnalysisReport.objects.filter(
        user=request.user,
        is_deleted_by_user=False,
        is_deleted_by_admin=False
    ).order_by('-analyzed_at')
    
    total_excellent = reports.filter(overall_verdict='excellent').count()
    total_good = reports.filter(overall_verdict='good').count()
    total_moderate = reports.filter(overall_verdict='moderate').count()
    total_avoid = reports.filter(overall_verdict='avoid').count()
    avg_score = reports.aggregate(Avg('overall_score'))['overall_score__avg'] or 0
    
    context = {
        'reports': reports,
        'total_reports': reports.count(),
        'total_excellent': total_excellent,
        'total_good': total_good,
        'total_moderate': total_moderate,
        'total_avoid': total_avoid,
        'avg_score': round(avg_score, 1),
    }
    return render(request, 'skin-report-history.html', context)

@login_required
def manage_products(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    products = Product.objects.all().order_by('-created_at')
    return render(request, 'admin/manage-products.html', {'products': products})

@login_required
def add_product(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save()
            messages.success(request, f'✨ Product "{product.name}" added successfully!')
            return redirect('manage-products')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = ProductForm()
    return render(request, 'admin/add-product.html', {'form': form})

@login_required
def edit_product(request, product_id):
    if not request.user.is_superuser:
        return redirect('dashboard')
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            remove_image = request.POST.get('remove_image') == 'on'
            if remove_image:
                if product.image and os.path.isfile(product.image.path):
                    os.remove(product.image.path)
                product.image = None
            elif 'image' in request.FILES:
                if product.image and os.path.isfile(product.image.path):
                    os.remove(product.image.path)
                product.image = request.FILES['image']
            product = form.save(commit=False)
            product.save()
            messages.success(request, f'✨ Product "{product.name}" updated successfully!')
            return redirect('manage-products')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm(instance=product)
    return render(request, 'admin/edit-product.html', {'form': form, 'product': product})

@login_required
def delete_product(request, product_id):
    if not request.user.is_superuser:
        return redirect('dashboard')
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        product_name = product.name
        product.delete()
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('manage-products')
    return render(request, 'admin/delete-product.html', {'product': product})

@login_required
def view_users(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    users = User.objects.filter(is_superuser=False).order_by('-date_joined')
    user_data = []
    for user in users:
        try:
            profile = user.userprofile
        except:
            profile = None
        user_data.append({'user': user, 'profile': profile})
    return render(request, 'admin/view-users.html', {'user_data': user_data})

@login_required
@require_http_methods(["POST", "GET"])
def admin_delete_user(request, user_id):
    if not request.user.is_superuser:
        messages.error(request, 'Admin privileges required.')
        return redirect('view-users')
    if request.method == 'GET':
        messages.error(request, 'Invalid request. Please use the delete button.')
        return redirect('view-users')
    try:
        user_to_delete = User.objects.get(id=user_id, is_superuser=False)
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
        return redirect('view-users')
    username = user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f'✅ User "{username}" permanently deleted.')
    return redirect('view-users')

@login_required
def view_reports(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    reports = AnalysisReport.objects.select_related('user').order_by('-analyzed_at')
    report_data = []
    for report in reports:
        ingredients = report.ingredients_data
        fixed = False
        for ing in ingredients:
            raw = ing.get('status')
            if raw is None:
                normalized = 'unknown'
                fixed = True
            else:
                normalized = str(raw).strip().lower()
                if normalized not in ('safe', 'moderate', 'harmful'):
                    normalized = 'unknown'
                    fixed = True
                elif normalized != raw:
                    fixed = True
            ing['status'] = normalized
        if fixed:
            report.ingredients_data = ingredients
            report.save()
        username_display = "admin" if report.user.is_superuser else report.user.username
        report_data.append({
            'report': report,
            'ingredients': ingredients,
            'ingredient_count': len(ingredients),
            'username_display': username_display,
        })
    context = {
        'reports': report_data,
        'total_reports': reports.count(),
        'safe_count': reports.filter(overall_status='safe').count(),
        'moderate_count': reports.filter(overall_status='moderate').count(),
        'harmful_count': reports.filter(overall_status='harmful').count(),
    }
    return render(request, 'admin/view-reports.html', context)

# @login_required
# def manage_ingredients(request):
#     if not request.user.is_superuser:
#         return redirect('dashboard')
#     ingredients = Ingredient.objects.all().order_by('name')
#     return render(request, 'admin/manage-ingredients.html', {'ingredients': ingredients})

@login_required
def manage_ingredients(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    
    # OPTIMIZED: Fetch only needed fields and paginate
    ingredients_list = Ingredient.objects.all().only('id', 'name', 'category', 'description').order_by('name')
    
    # Pagination - 25 items per page (better performance)
    paginator = Paginator(ingredients_list, 25)
    page_number = request.GET.get('page', 1)
    ingredients = paginator.get_page(page_number)
    
    # ✅ FIXED: Added total_count to context
    return render(request, 'admin/manage-ingredients.html', {
        'ingredients': ingredients,
        'total_count': Ingredient.objects.count(),  # THIS WAS MISSING!
    })


@login_required
def add_ingredient(request):
    if not request.user.is_superuser:
        return redirect('dashboard')
    if request.method == 'POST':
        form = IngredientForm(request.POST)
        if form.is_valid():
            ingredient = form.save()
            messages.success(request, f'Ingredient "{ingredient.name}" added successfully!')
            return redirect('manage-ingredients')
    else:
        form = IngredientForm()
    return render(request, 'admin/add-ingredient.html', {'form': form})

@login_required
def edit_ingredient(request, ingredient_id):
    if not request.user.is_superuser:
        return redirect('dashboard')
    ingredient = get_object_or_404(Ingredient, id=ingredient_id)
    if request.method == 'POST':
        form = IngredientForm(request.POST, instance=ingredient)
        if form.is_valid():
            form.save()
            messages.success(request, f'Ingredient "{ingredient.name}" updated successfully!')
            return redirect('manage-ingredients')
    else:
        form = IngredientForm(instance=ingredient)
    return render(request, 'admin/edit-ingredient.html', {'form': form, 'ingredient': ingredient})

@login_required
def delete_ingredient(request, ingredient_id):
    if not request.user.is_superuser:
        return redirect('dashboard')
    ingredient = get_object_or_404(Ingredient, id=ingredient_id)
    if request.method == 'POST':
        ingredient_name = ingredient.name
        ingredient.delete()
        messages.success(request, f'Ingredient "{ingredient_name}" deleted successfully!')
        return redirect('manage-ingredients')
    return render(request, 'admin/delete-ingredient.html', {'ingredient': ingredient})

@login_required
def user_logout(request):
    logout(request)
    messages.success(request, 'You have been logged out successfully. 👋')
    return redirect('login')

# ------------------- SKINCARE ANALYZER (ENHANCED) -------------------
@login_required
def skincare_analyzer(request):
    skin_profile, created = UserSkinProfile.objects.get_or_create(user=request.user, defaults={'skin_type': 'normal'})
    if request.method == 'POST':
        product_name = request.POST.get('product_name', '').strip()
        ingredients_text = request.POST.get('ingredients', '').strip()
        user_skin_type = request.POST.get('skin_type', skin_profile.skin_type)
        if user_skin_type != skin_profile.skin_type:
            skin_profile.skin_type = user_skin_type
            skin_profile.save()
        if not product_name or not ingredients_text:
            messages.error(request, 'Please provide both product name and ingredients.')
            return redirect('skincare-analyzer')
        analysis_result = perform_enhanced_skincare_analysis(ingredients_text, user_skin_type, product_name)
        report = SkinAnalysisReport.objects.create(
            user=request.user,
            product_name=product_name,
            user_skin_type=user_skin_type,
            ingredients_analyzed=analysis_result.get('ingredients', []),
            overall_score=analysis_result.get('overall_score', 0),
            skin_compatibility_score=analysis_result.get('skin_compatibility_score', 0),
            safety_score=analysis_result.get('safety_score', 0),
            efficacy_score=analysis_result.get('efficacy_score', 0),
            safe_count=analysis_result.get('safe_count', 0),
            moderate_count=analysis_result.get('moderate_count', 0),
            harmful_count=analysis_result.get('harmful_count', 0),
            scientifically_approved_count=analysis_result.get('scientifically_approved_count', 0),
            dermatologist_recommended_count=analysis_result.get('dermatologist_recommended_count', 0),
            overall_verdict=analysis_result.get('overall_verdict', 'moderate'),
            recommendation_summary=analysis_result.get('recommendation_summary', ''),
            skin_specific_advice=analysis_result.get('skin_specific_advice', ''),
            alternatives_suggested=analysis_result.get('alternatives_suggested', [])
        )
        AnalysisReport.objects.create(
            user=request.user,
            product_name=product_name,
            ingredients_data=analysis_result.get('ingredients', []),
            safe_ingredients=analysis_result.get('safe_count', 0),
            moderate_ingredients=analysis_result.get('moderate_count', 0),
            harmful_ingredients=analysis_result.get('harmful_count', 0),
            overall_status=analysis_result.get('overall_verdict', 'moderate'),
            recommendation=analysis_result.get('recommendation_summary', ''),
            is_deleted_by_user=False
        )
        messages.success(request, f'✨ Professional analysis complete for "{product_name}"!')
        return render(request, 'skincare-analyzer-result.html', {
            'result': analysis_result,
            'product_name': product_name,
            'report_id': report.id,
            'user_skin_type': user_skin_type
        })
    context = {
        'skin_profile': skin_profile,
        'skin_types': SkinTypeRecommendation.SKIN_TYPES,
        'skin_concerns': ['Acne', 'Aging', 'Dryness', 'Oiliness', 'Hyperpigmentation', 'Redness', 'Dullness']
    }
    return render(request, 'skincare-analyzer.html', context)

def perform_enhanced_skincare_analysis(ingredients_text, skin_type, product_name):
    ingredients_list = [i.strip() for i in ingredients_text.split(',') if i.strip()]
    ingredients_for_analysis = []
    for ingredient_name in ingredients_list:
        ingredient = Ingredient.objects.filter(name__iexact=ingredient_name).first()
        skin_compatibility = 70
        if ingredient:
            skin_rec = SkinTypeRecommendation.objects.filter(ingredient=ingredient, skin_type=skin_type).first()
            if skin_rec:
                skin_compatibility = skin_rec.suitability_score
            else:
                skin_compatibility = 70
        else:
            skin_compatibility = calculate_skin_compatibility(ingredient_name, skin_type)
        scientific_approval = {'has_approval': False}
        if ingredient:
            scientific = ScientificApproval.objects.filter(ingredient=ingredient).first()
            if scientific and scientific.is_active:
                scientific_approval = {
                    'has_approval': True,
                    'level': scientific.get_approval_level_display(),
                    'certifying_body': scientific.certifying_body,
                    'is_clinical': scientific.approval_level in ['clinical', 'research']
                }
        derm_suggestions = []
        derm_recommended = False
        if ingredient:
            derm_sugs = list(DermatologistSuggestion.objects.filter(ingredient=ingredient))
            for ds in derm_sugs:
                derm_suggestions.append({
                    'type': ds.suggestion_type,
                    'text': ds.suggestion_text,
                    'dermatologist': ds.dermatologist_name
                })
            derm_recommended = len(derm_sugs) > 0
        ingredients_for_analysis.append({
            'name': ingredient_name,
            'skin_compatibility': skin_compatibility,
            'scientific_approval': scientific_approval,
            'dermatologist_suggestions': derm_suggestions,
            'dermatologist_recommended': derm_recommended
        })
    result = analyze_product_ingredients(ingredients_for_analysis, skin_type)
    if 'skin_specific_advice' not in result:
        result['skin_specific_advice'] = generate_skin_specific_advice(result.get('ingredients', []), skin_type)
    if 'alternatives_suggested' not in result:
        result['alternatives_suggested'] = []
    if 'total_ingredients' not in result:
        result['total_ingredients'] = len(ingredients_list)
    return result

def calculate_skin_compatibility(ingredient_name, skin_type):
    name_lower = ingredient_name.lower()
    compatibility = 50
    hydrators = ['glycerin', 'hyaluronic acid', 'sodium hyaluronate', 'panthenol', 'butylene glycol', 'propanediol', 'sorbitol', 'trehalose', 'urea']
    for h in hydrators:
        if h in name_lower:
            compatibility += 25
    if 'ceramide' in name_lower:
        compatibility += 30 if skin_type in ['dry', 'sensitive'] else 15
    if 'niacinamide' in name_lower:
        if skin_type == 'oily':
            compatibility += 30
        elif skin_type == 'sensitive':
            compatibility += 15
        else:
            compatibility += 20
    non_comedogenic = ['jojoba', 'argan', 'rosehip', 'hemp seed', 'grapeseed', 'squalane', 'marula', 'baobab', 'sunflower', 'safflower']
    for oil in non_comedogenic:
        if oil in name_lower:
            compatibility += 20 if skin_type == 'oily' else (10 if skin_type == 'dry' else 15)
    comedogenic = ['coconut', 'olive', 'avocado', 'castor', 'cocoa butter']
    for oil in comedogenic:
        if oil in name_lower:
            compatibility += -25 if skin_type == 'oily' else (10 if skin_type == 'dry' else 5)
    acids = ['salicylic acid', 'glycolic acid', 'lactic acid', 'mandelic acid', 'kojic acid']
    for a in acids:
        if a in name_lower:
            compatibility += 20 if skin_type == 'oily' else (-30 if skin_type == 'sensitive' else (-15 if skin_type == 'dry' else 5))
    retinoids = ['retinol', 'retinal', 'tretinoin', 'adapalene']
    for r in retinoids:
        if r in name_lower:
            compatibility += -25 if skin_type == 'sensitive' else (15 if skin_type == 'oily' else 5)
    alcohols = ['alcohol denat', 'denatured alcohol', 'ethanol', 'isopropyl alcohol']
    for alc in alcohols:
        if alc in name_lower:
            compatibility += -45 if skin_type == 'sensitive' else (-40 if skin_type == 'dry' else -25)
    fragrances = ['fragrance', 'parfum', 'perfume', 'limonene', 'linalool']
    for f in fragrances:
        if f in name_lower:
            compatibility += -40 if skin_type == 'sensitive' else -15
    sulfates = ['sodium lauryl sulfate', 'sls', 'sodium laureth sulfate', 'sles']
    for s in sulfates:
        if s in name_lower:
            compatibility += -50 if skin_type == 'sensitive' else (-45 if skin_type == 'dry' else -30)
    sunscreens = ['zinc oxide', 'titanium dioxide', 'avobenzone', 'octocrylene']
    for sun in sunscreens:
        if sun in name_lower:
            compatibility += 20
    soothing = ['aloe', 'chamomile', 'calendula', 'bisabolol', 'allantoin', 'madecassoside', 'centella asiatica', 'cica', 'panthenol', 'oat']
    for s in soothing:
        if s in name_lower:
            compatibility += 35 if skin_type == 'sensitive' else 15
    antioxidants = ['vitamin c', 'ascorbic acid', 'vitamin e', 'tocopherol', 'ferulic acid', 'resveratrol', 'green tea']
    for a in antioxidants:
        if a in name_lower:
            compatibility += 15
    if name_lower in ['water', 'aqua']:
        compatibility = 70
    return max(0, min(100, compatibility))

def get_default_skin_advice(ingredient_name, skin_type):
    name_lower = ingredient_name.lower()
    if skin_type == 'oily':
        if 'oil' in name_lower and 'essential' not in name_lower:
            return "May be comedogenic for oily skin. Check non-comedogenic rating."
        elif 'acid' in name_lower:
            return "Good for exfoliation. Start with low concentration."
        else:
            return "Generally suitable for oily skin. Look for oil-free formulations."
    elif skin_type == 'dry':
        if 'hyaluronic' in name_lower or 'glycerin' in name_lower:
            return "Excellent hydrator for dry skin. Apply to damp skin."
        elif 'alcohol' in name_lower and 'cetearyl' not in name_lower:
            return "May be drying. Look for moisturizing alternatives."
        else:
            return "Generally suitable for dry skin. Follow with moisturizer."
    elif skin_type == 'sensitive':
        if 'fragrance' in name_lower or 'parfum' in name_lower:
            return "Potential irritant. Avoid if you have sensitive skin."
        elif 'alcohol' in name_lower and 'cetearyl' not in name_lower:
            return "May cause irritation. Patch test before use."
        else:
            return "Patch test recommended for sensitive skin."
    else:
        return "Generally suitable for normal to combination skin."

@login_required
def skin_report_detail(request, report_id):
    if request.user.is_superuser:
        report = get_object_or_404(SkinAnalysisReport, id=report_id)
    else:
        report = get_object_or_404(SkinAnalysisReport, id=report_id, user=request.user)
    context = {
        'report': report,
        'ingredients': report.ingredients_analyzed,
        'skin_type_display': dict(SkinTypeRecommendation.SKIN_TYPES).get(report.user_skin_type, 'Not specified'),
        'verdict_display': {
            'excellent': {'class': 'excellent', 'icon': '🌟', 'text': 'Excellent Choice'},
            'good': {'class': 'good', 'icon': '✅', 'text': 'Good Choice'},
            'moderate': {'class': 'moderate', 'icon': '⚠️', 'text': 'Use with Caution'},
            'avoid': {'class': 'avoid', 'icon': '❌', 'text': 'Avoid'}
        }.get(report.overall_verdict, {'class': 'moderate', 'icon': '⚠️', 'text': 'Use with Caution'})
    }
    return render(request, 'skin-report-detail.html', context)

@login_required
def skin_profile_setup(request):
    profile, created = UserSkinProfile.objects.get_or_create(user=request.user, defaults={'skin_type': 'normal'})
    if request.method == 'POST':
        profile.skin_type = request.POST.get('skin_type', 'normal')
        profile.skin_concerns = request.POST.getlist('skin_concerns')
        profile.allergies = request.POST.getlist('allergies')
        profile.save()
        messages.success(request, '✨ Your skin profile has been updated!')
        return redirect('skincare-analyzer')
    context = {
        'profile': profile,
        'skin_types': SkinTypeRecommendation.SKIN_TYPES,
        'common_concerns': ['Acne', 'Aging', 'Dryness', 'Oiliness', 'Hyperpigmentation', 'Redness', 'Dullness', 'Uneven Texture'],
        'common_allergies': ['Nuts', 'Fragrance', 'Essential Oils', 'Lanolin', 'Parabens', 'Sulfates', 'Alcohol']
    }
    return render(request, 'skin-profile-setup.html', context)

@login_required
def ingredient_scientific_info(request, ingredient_name):
    ingredient = get_object_or_404(Ingredient, name__iexact=ingredient_name)
    scientific = ScientificApproval.objects.filter(ingredient=ingredient).first()
    derm_suggestions = DermatologistSuggestion.objects.filter(ingredient=ingredient)
    skin_recs = SkinTypeRecommendation.objects.filter(ingredient=ingredient)
    context = {
        'ingredient': ingredient,
        'scientific': scientific,
        'derm_suggestions': derm_suggestions,
        'skin_recommendations': skin_recs,
    }
    return render(request, 'ingredient-scientific-info.html', context)

@login_required
def ingredient_search_api(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'results': []})
    ingredients = Ingredient.objects.filter(Q(name__icontains=query) | Q(description__icontains=query))[:20]
    results = [{
        'name': ing.name,
        'category': ing.category,
        'description': ing.description[:100] + '...' if len(ing.description) > 100 else ing.description,
        'scientific_approved': ScientificApproval.objects.filter(ingredient=ing, approval_level__in=['fda', 'eu', 'clinical']).exists()
    } for ing in ingredients]
    return JsonResponse({'results': results})

def classify_unknown_ingredient(ingredient_name):
    harmful_keywords = ['paraben', 'sulfate', 'phthalate', 'formaldehyde', 'alcohol denat', 'fragrance', 'perfume', 'mineral oil', 'paraffin', 'triclosan']
    moderate_keywords = ['alcohol', 'essential oil', 'citrus', 'menthol', 'linalool', 'limonene']
    name_lower = ingredient_name.lower()
    for keyword in harmful_keywords:
        if keyword in name_lower:
            return 'harmful'
    for keyword in moderate_keywords:
        if keyword in name_lower:
            return 'moderate'
    return 'safe'

def generate_recommendation_summary(ingredients, verdict, score):
    harmful_ings = [i for i in ingredients if i['status'] == 'harmful']
    moderate_ings = [i for i in ingredients if i['status'] == 'moderate']
    scientifically_approved = [i for i in ingredients if i['scientific_approval']['has_approval']]
    if verdict == 'excellent':
        return f"This product is an EXCELLENT choice for your skin. Score: {score}/100. It contains {len(scientifically_approved)} scientifically-approved ingredients and no harmful components. The formulation is well-balanced and skin-friendly."
    elif verdict == 'good':
        return f"This is a GOOD product with a score of {score}/100. It contains {len(scientifically_approved)} clinically-proven ingredients. However, consider the {len(moderate_ings)} moderate-risk ingredients that may cause sensitivity."
    elif verdict == 'moderate':
        return f"USE WITH CAUTION - Score: {score}/100. The product contains {len(moderate_ings)} ingredients that may cause reactions. We recommend patch testing before full application."
    else:
        harmful_names = [i['name'] for i in harmful_ings[:3]]
        return f"AVOID THIS PRODUCT - Score: {score}/100. It contains {len(harmful_ings)} potentially harmful ingredients including {', '.join(harmful_names)}. These ingredients are known to cause skin damage, irritation, or long-term health concerns."

def generate_skin_specific_advice(ingredients, skin_type):
    skin_type_names = {'oily': 'Oily Skin', 'dry': 'Dry Skin', 'combination': 'Combination Skin', 'normal': 'Normal Skin', 'sensitive': 'Sensitive Skin'}
    skin_emojis = {'oily': '🔥', 'dry': '💧', 'combination': '🔄', 'normal': '✨', 'sensitive': '🌸'}
    harmful_ingredients = []
    moderate_ingredients = []
    good_ingredients = []
    for ing in ingredients:
        name = ing.get('name', '')
        status = ing.get('status', 'safe')
        if status == 'harmful':
            harmful_ingredients.append({'name': name, 'reason': ing.get('harmful_reason', 'Known skin irritant or unsafe ingredient')})
        elif status == 'moderate':
            moderate_ingredients.append(name)
        name_lower = name.lower()
        if skin_type == 'oily':
            if any(x in name_lower for x in ['coconut oil', 'cocoa butter', 'mineral oil', 'paraffin', 'lanolin']):
                if name not in moderate_ingredients:
                    moderate_ingredients.append(name)
            elif any(x in name_lower for x in ['salicylic acid', 'niacinamide', 'hyaluronic acid', 'glycerin']):
                if status != 'harmful':
                    good_ingredients.append(name)
        elif skin_type == 'dry':
            if any(x in name_lower for x in ['alcohol denat', 'denatured alcohol', 'sd alcohol', 'ethanol']):
                if name not in moderate_ingredients:
                    moderate_ingredients.append(name)
            elif any(x in name_lower for x in ['hyaluronic acid', 'glycerin', 'ceramide', 'squalane', 'shea butter']):
                if status != 'harmful':
                    good_ingredients.append(name)
        elif skin_type == 'combination':
            if any(x in name_lower for x in ['coconut oil', 'mineral oil', 'alcohol denat']):
                if name not in moderate_ingredients:
                    moderate_ingredients.append(name)
        elif skin_type == 'sensitive':
            if any(x in name_lower for x in ['fragrance', 'parfum', 'perfume', 'alcohol denat', 'essential oil', 'limonene', 'linalool', 'citrus']):
                if name not in moderate_ingredients:
                    moderate_ingredients.append(name)
            elif any(x in name_lower for x in ['aloe', 'chamomile', 'centella', 'cica', 'panthenol', 'allantoin', 'oat']):
                if status != 'harmful':
                    good_ingredients.append(name)
    if harmful_ingredients:
        harmful_names = ', '.join([h['name'] for h in harmful_ingredients[:3]])
        advice = f"""**⚠️ CRITICAL SAFETY ALERT - AVOID THIS PRODUCT**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 **HARMFUL INGREDIENTS DETECTED:**
The following ingredient(s) in this product are classified as HARMFUL:
• {harmful_names}

**WHY YOU SHOULD AVOID THIS PRODUCT:**

"""
        for h in harmful_ingredients[:2]:
            advice += f"❌ **{h['name']}:** {h['reason']}\n"
        advice += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **DERMATOLOGIST WARNING:**

• This product contains ingredients that can cause:
  - Severe skin irritation and contact dermatitis
  - Allergic reactions (redness, swelling, itching)
  - Potential long-term skin barrier damage
  - Increased skin sensitivity to UV radiation

• **SKIN COMPATIBILITY SCORE: 0%** - This product is NOT recommended for any skin type

• **DERMATOLOGIST RECOMMENDATION: AVOID COMPLETELY**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔬 **SAFER ALTERNATIVES:**

Instead of this product, look for formulations containing:
• Hypoallergenic ingredients
• Fragrance-free formulas
• Dermatologist-tested products
• Non-comedogenic labels (for oily/acne-prone skin)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ **IF YOU HAVE USED THIS PRODUCT:**
Discontinue use immediately. If you experience rash, burning, or severe dryness, consult a dermatologist.
"""
        return advice
    advice = f"""**{skin_emojis.get(skin_type, '✨')} Professional Analysis for {skin_type_names.get(skin_type, skin_type)}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 **INGREDIENT COMPATIBILITY CHECK**

"""
    if good_ingredients:
        good_list = ', '.join(good_ingredients[:3])
        advice += f"✅ **Beneficial Ingredients Found:** {good_list}\n   These ingredients work synergistically with your skin type.\n\n"
    if moderate_ingredients:
        moderate_list = ', '.join(moderate_ingredients[:3])
        advice += f"⚠️ **Ingredients to Monitor:** {moderate_list}\n   May cause sensitivity for {skin_type_names.get(skin_type, skin_type)}. Patch test recommended.\n\n"
    if not good_ingredients and not moderate_ingredients:
        advice += "📊 **Neutral Profile:** No specific beneficial or concerning ingredients identified for your skin type.\n\n"
    advice += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    advice += "🔬 **CLINICAL RECOMMENDATIONS**\n\n"
    if skin_type == 'oily':
        advice += """• **Sebum Regulation:** This product's formulation may affect sebaceous gland activity
• **Comedogenicity Check:** Look for "non-comedogenic" labeling on future purchases
• **Optimal Formulations:** Oil-free, water-based, or gel formulations are preferred
• **Key Ingredients to Seek:** Salicylic acid (0.5-2%), niacinamide (2-5%), zinc PCA
• **Ingredients to Avoid:** Heavy occlusives (coconut oil, cocoa butter, mineral oil)"""
    elif skin_type == 'dry':
        advice += """• **Hydration Assessment:** Evaluate if this product provides adequate humectants and emollients
• **Barrier Support:** Look for ceramides, fatty acids, and cholesterol in moisturizers
• **Avoid Astringents:** High alcohol content can compromise skin barrier function
• **Application Technique:** Apply to slightly damp skin for enhanced absorption
• **Layering Strategy:** Follow with an occlusive moisturizer to prevent TEWL"""
    elif skin_type == 'combination':
        advice += """• **Zonal Application:** This product may require different application in T-zone vs. U-zone
• **Multi-Masking Approach:** Consider using lighter formulas on forehead, nose, chin
• **Hydration Focus:** Use richer formulations on cheeks and jawline
• **Balanced Formulations:** Seek products with medium-weight emollients
• **Monitoring:** Observe each facial zone independently for reactions"""
    elif skin_type == 'normal':
        advice += """• **Maintenance Protocol:** Normal skin tolerates most ingredients well
• **Avoid Extremes:** Steer clear of overly heavy occlusives or harsh astringents
• **Preventative Focus:** Prioritize antioxidants (vitamin C, E, ferulic acid)
• **Sun Protection:** Daily SPF 30+ is essential regardless of product use
• **Patch Testing:** Still recommended when introducing new active ingredients"""
    elif skin_type == 'sensitive':
        advice += """• **SENSITIVE SKIN PROTOCOL - Patch Test Required Before Use!**
• **Test Site:** Apply small amount behind ear or on inner antecubital fossa
• **Observation Period:** Minimum 48-72 hours before facial application
• **Avoid Triggers:** No fragrance, essential oils, denatured alcohol, or harsh preservatives
• **Discontinue Immediately:** If erythema, pruritus, burning, or stinging occurs
• **Seek Labels:** "Hypoallergenic", "Fragrance-Free", "Dermatologist Tested"
• **Emergency:** Severe reactions require immediate dermatology consultation"""
    advice += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    advice += "🧪 **STANDARDIZED PATCH TEST PROTOCOL**\n\n"
    advice += """Before incorporating any new skincare product, follow this clinical patch test method:

**Step 1:** Cleanse a 2cm x 2cm area on your inner forearm or postauricular area (behind ear)

**Step 2:** Apply a pea-sized amount of product to the test area

**Step 3:** Cover with an occlusive dressing (adhesive patch) for 24 hours

**Step 4:** Remove patch and assess for any reaction at 24, 48, and 72 hours

**Step 5:** Evaluate for:
   - Erythema (redness)
   - Edema (swelling)
   - Vesiculation (blisters)
   - Pruritus (itching)
   - Burning sensation

**If NO reaction occurs after 72 hours:** The product is likely safe for facial use.

**If ANY adverse reaction occurs:** Discontinue use immediately. Consult a dermatologist if symptoms persist beyond 48 hours.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*This analysis is based on current dermatological literature. Individual responses may vary.*"""
    return advice

def analyze_product_ingredients(ingredients_list, skin_type):
    from .utils import StaticIngredientAnalyzer as StaticIA
    safe_count = moderate_count = harmful_count = scientifically_approved_count = dermatologist_recommended_count = 0
    analyzed_ingredients = []
    for ing in ingredients_list:
        ing_name = ing.get('name', 'Unknown')
        ing_name_lower = ing_name.lower()
        static_result = StaticIA.analyze_ingredients(ing_name, 'skincare')
        if static_result and static_result.get('ingredients'):
            static_ing = static_result['ingredients'][0]
            static_status = static_ing.get('status', 'unknown')
            static_description = static_ing.get('description', '')
            static_side_effects = static_ing.get('side_effects', '')
        else:
            static_status = 'unknown'
            static_description = ''
            static_side_effects = ''
        is_banned = any(banned in ing_name_lower for banned in StaticIA.BANNED_INGREDIENTS)
        is_medical_risk = any(medical in ing_name_lower for medical in StaticIA.MEDICAL_RISK_INGREDIENTS)
        is_fragrance = any(fragrance in ing_name_lower for fragrance in StaticIA.FRAGRANCE_ALLERGENS)
        if is_banned or is_medical_risk:
            status = 'harmful'
            skin_compatibility = 0
            harmful_count += 1
        elif is_fragrance:
            status = 'moderate'
            skin_compatibility = 50
            moderate_count += 1
        elif static_status == 'harmful':
            status = 'harmful'
            skin_compatibility = 10
            harmful_count += 1
        elif static_status == 'moderate':
            status = 'moderate'
            skin_compatibility = 50
            moderate_count += 1
        elif static_status == 'safe':
            status = 'safe'
            base_score = ing.get('skin_compatibility', 75)
            if base_score >= 90:
                skin_compatibility = min(100, base_score)
            else:
                skin_compatibility = min(89, max(65, base_score))
            safe_count += 1
        elif static_status == 'unknown':
            status = 'moderate'
            skin_compatibility = 45
            moderate_count += 1
        else:
            status = 'moderate'
            skin_compatibility = 50
            moderate_count += 1
        scientific_approval = StaticIA.get_scientific_approval(ing_name)
        if scientific_approval.get('has_approval'):
            scientifically_approved_count += 1
        derm_suggestions = StaticIA.get_dermatologist_suggestions(ing_name, skin_type)
        analyzed_ingredient = {
            'name': ing_name,
            'status': status,
            'status_icon': '❌' if status == 'harmful' else ('⚠️' if status == 'moderate' else '✅'),
            'skin_compatibility': skin_compatibility,
            'skin_compatibility_label': get_compatibility_label(skin_compatibility),
            'scientific_approval': {
                'has_approval': scientific_approval.get('has_approval', False),
                'level': scientific_approval.get('level', 'Not Approved'),
                'certifying_body': scientific_approval.get('certifying_body', ''),
                'is_clinical': scientific_approval.get('is_clinical', False)
            },
            'dermatologist_suggestions': derm_suggestions,
            'skin_recommendation': ing.get('skin_recommendation', None),
            'description': static_description or ing.get('description', 'Information from safety database'),
            'side_effects': static_side_effects or ing.get('side_effects', 'No documented side effects')
        }
        analyzed_ingredients.append(analyzed_ingredient)
    if harmful_count > 0:
        dermatologist_recommended_count = 0
    else:
        for ing in analyzed_ingredients:
            if ing['status'] != 'harmful' and ing.get('dermatologist_suggestions'):
                dermatologist_recommended_count += 1
    total_ingredients = len(analyzed_ingredients)
    if harmful_count > 0:
        overall_score = max(5, min(20, 20 - (harmful_count * 3)))
        safety_score = overall_score
        efficacy_score = max(5, min(20, 15 - (harmful_count * 2)))
        overall_verdict = 'avoid'
        skin_compatibility_score = max(5, min(20, 15 - (harmful_count * 2)))
        recommendation_summary = f"""

║ 🚨 CRITICAL SAFETY ALERT - DERMATOLOGIST DOES NOT RECOMMEND THIS PRODUCT 🚨 ║


🔴 PRODUCT VERDICT: HARMFUL - DO NOT USE

⚠️ HARMFUL INGREDIENTS DETECTED: {harmful_count} harmful ingredient(s)

❌ DERMATOLOGIST RECOMMENDATION: 0/10 - NOT RECOMMENDED

📊 PRODUCT SCORE: {overall_score}/100 (🔴 CRITICAL - BELOW 20%)

🎯 SKIN COMPATIBILITY: {skin_compatibility_score}% (🔴 UNSAFE)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ **WHY YOU SHOULD AVOID THIS PRODUCT:**
• Contains ingredients that can cause severe skin irritation
• May trigger allergic reactions (redness, swelling, itching)
• Potential long-term skin barrier damage
• Not approved by dermatologists for safe use

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔬 **IMMEDIATE ACTION REQUIRED:**
• DISCONTINUE USE IMMEDIATELY if you have started using this product
• Consult a dermatologist if you experience any adverse reactions
• Look for products with cleaner ingredient profiles
"""
    else:
        if total_ingredients > 0:
            overall_score = int((safe_count / total_ingredients) * 80 + (scientifically_approved_count / total_ingredients) * 15 + (dermatologist_recommended_count / total_ingredients) * 5)
            safety_score = int((safe_count / total_ingredients) * 100)
            efficacy_score = int((scientifically_approved_count / total_ingredients) * 50 + (dermatologist_recommended_count / total_ingredients) * 30)
        else:
            overall_score = safety_score = efficacy_score = 50
        if moderate_count > 0 and total_ingredients > 0:
            reduction = int((moderate_count / total_ingredients) * 15)
            overall_score = max(40, overall_score - reduction)
            safety_score = max(40, safety_score - reduction)
        if overall_score >= 90:
            overall_verdict = 'excellent'
        elif overall_score >= 65:
            overall_verdict = 'good'
        elif overall_score >= 40:
            overall_verdict = 'moderate'
        else:
            overall_verdict = 'avoid'
        if total_ingredients > 0:
            skin_compatibility_score = int(sum(ing['skin_compatibility'] for ing in analyzed_ingredients) / total_ingredients)
        else:
            skin_compatibility_score = 50
        if overall_verdict == 'excellent':
            recommendation_summary = f"""

║  🌟 EXCELLENT CHOICE - Dermatologist Recommended 🌟  ║


🟢 PRODUCT VERDICT: EXCELLENT - SAFE TO USE

📊 PRODUCT SCORE: {overall_score}/100 (🟢 EXCELLENT - 90-100%)

✅ SAFE INGREDIENTS: {safe_count}
🔬 CLINICALLY PROVEN: {scientifically_approved_count}
👨‍⚕️ DERM-RECOMMENDED: {dermatologist_recommended_count}

🎯 SKIN COMPATIBILITY: {skin_compatibility_score}% (🟢 EXCELLENT MATCH)

✅ This formulation is well-balanced and free from harmful components.
✅ Highly compatible with {skin_type} skin.
✅ Recommended by dermatologists for daily use.
"""
        elif overall_verdict == 'good':
            recommendation_summary = f"""

║  👍 GOOD CHOICE - Generally Safe for Your Skin  ║


🟢 PRODUCT VERDICT: GOOD - SAFE TO USE

📊 PRODUCT SCORE: {overall_score}/100 (🟢 GOOD - 65-89%)

✅ SAFE INGREDIENTS: {safe_count}
⚠️ MODERATE RISK INGREDIENTS: {moderate_count}

🎯 SKIN COMPATIBILITY: {skin_compatibility_score}% (🟢 GOOD COMPATIBILITY)

⚠️ RECOMMENDATION: Perform a patch test before full application.
✅ Suitable for {skin_type} skin with normal tolerance.
"""
        elif overall_verdict == 'moderate':
            recommendation_summary = f"""

║  ⚠️ USE WITH CAUTION - Patch Test Required                  ║


🟠 PRODUCT VERDICT: MODERATE RISK

📊 PRODUCT SCORE: {overall_score}/100 (🟠 MODERATE - 40-64%)

⚠️ MODERATE RISK INGREDIENTS: {moderate_count}

🎯 SKIN COMPATIBILITY: {skin_compatibility_score}% (🟠 CAUTION)

🔬 Patch testing is MANDATORY before use.
⚠️ May cause sensitivity in some individuals with {skin_type} skin.
"""
        else:
            recommendation_summary = f"""

║  ⚠️ USE WITH CAUTION - Unknown Ingredients  ║


🟠 PRODUCT VERDICT: MODERATE RISK

📊 PRODUCT SCORE: {overall_score}/100 (🟠 MODERATE)

⚠️ Some ingredients have not been fully verified.

🎯 SKIN COMPATIBILITY: {skin_compatibility_score}%

🔬 Patch test recommended before use.
"""
    return {
        'overall_score': overall_score,
        'overall_verdict': overall_verdict,
        'safe_count': safe_count,
        'moderate_count': moderate_count,
        'harmful_count': harmful_count,
        'scientifically_approved_count': scientifically_approved_count,
        'dermatologist_recommended_count': dermatologist_recommended_count,
        'skin_compatibility_score': skin_compatibility_score,
        'safety_score': safety_score,
        'efficacy_score': efficacy_score,
        'recommendation_summary': recommendation_summary,
        'ingredients': analyzed_ingredients,
        'total_ingredients': total_ingredients
    }

def get_compatibility_label(score):
    if score >= 90:
        return '🟢 EXCELLENT - Highly Compatible'
    elif score >= 65:
        return '🟢 GOOD - Suitable'
    elif score >= 40:
        return '🟠 CAUTION - Patch Test Required'
    else:
        return '🔴 CRITICAL - AVOID'

@login_required
def admin_bulk_delete_reports(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    if request.method == 'POST':
        report_ids = json.loads(request.POST.get('report_ids', '[]'))
        deleted_count = 0
        deleted_names = []
        for report_id in report_ids:
            try:
                report = AnalysisReport.objects.get(id=report_id)
                deleted_names.append(report.product_name)
                report.delete()
                deleted_count += 1
            except AnalysisReport.DoesNotExist:
                pass
        if deleted_count > 0:
            messages.success(request, f'🗑️ Successfully deleted {deleted_count} report(s): {", ".join(deleted_names[:3])}{"..." if len(deleted_names) > 3 else ""}')
        else:
            messages.warning(request, 'No reports were deleted.')
        return redirect('view-reports')
    return redirect('view-reports')

@login_required
def admin_skin_bulk_delete(request):
    if not request.user.is_superuser:
        messages.error(request, 'Access denied! Admin privileges required.')
        return redirect('dashboard')
    if request.method == 'POST':
        report_ids = json.loads(request.POST.get('report_ids', '[]'))
        deleted_count = 0
        deleted_names = []
        for report_id in report_ids:
            try:
                report = SkinAnalysisReport.objects.get(id=report_id)
                deleted_names.append(report.product_name)
                report.delete()
                deleted_count += 1
            except SkinAnalysisReport.DoesNotExist:
                pass
        if deleted_count > 0:
            messages.success(request, f'🗑️ Successfully deleted {deleted_count} skin report(s): {", ".join(deleted_names[:3])}{"..." if len(deleted_names) > 3 else ""}')
        else:
            messages.warning(request, 'No reports were deleted.')
        return redirect('admin-skin-reports')
    return redirect('admin-skin-reports')