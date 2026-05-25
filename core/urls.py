from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # ===== CUSTOM ADMIN URLS (MUST BE FIRST) =====
    path('custom-skin-reports/', views.admin_skin_reports, name='admin-skin-reports'),
    path('custom-reports/delete/<int:report_id>/', views.admin_delete_report_permanent, name='admin-delete-report'),
    path('custom-reports/restore/<int:report_id>/', views.admin_restore_report, name='admin-restore-report'),
    path('custom-skin-reports/delete/<int:report_id>/', views.admin_skin_delete_report_permanent, name='admin-skin-delete-report'),
    path('custom-skin-reports/restore/<int:report_id>/', views.admin_skin_restore_report, name='admin-skin-restore-report'),
    
    # ✅ ADD THIS - Bulk delete URL (matches template)
    path('dashboard/bulk-delete-reports/', views.admin_bulk_delete_reports, name='dashboard-bulk-delete-reports'),
    path('dashboard/skin-bulk-delete/', views.admin_skin_bulk_delete, name='admin-skin-bulk-delete'),
   
    
    # ===== DEFAULT DJANGO ADMIN =====
    path('admin/', admin.site.urls),
    
    # ===== AUTH =====
    path('', views.index, name='index'),
    path('register/', views.user_register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('forgot-password/', views.forgot_password, name='forgot-password'),
    path('verify-otp/', views.verify_otp, name='verify-otp'),
    path('reset-password/', views.reset_password, name='reset-password'),

    # ===== DASHBOARD & PROFILE =====
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile, name='profile'),

    # ===== PRODUCT =====
    path('search/', views.search_product, name='search-product'),
    path('product/<int:product_id>/', views.product_detail, name='product-detail'),

    # ===== ANALYZER =====
    path('analyzer/', views.analyzer, name='analyzer'),
    path('report/<int:report_id>/', views.report, name='report'),
    path('report-history/', views.report_history, name='report-history'),
    path('delete-report/<int:report_id>/', views.delete_report, name='delete_report'),

    # ===== FILTERS =====
    path('filter-by/<str:status>/', views.filter_by_status, name='filter-by-status'),
    path('ingredients/<str:status>/', views.ingredient_detail_list, name='ingredient-detail-list'),

    # ===== ADMIN MANAGEMENT =====
   
    path('admin-dashboard/', views.admin_dashboard, name='admin-dashboard'),
    path('manage-products/', views.manage_products, name='manage-products'),
    path('add-product/', views.add_product, name='add-product'),
    path('edit-product/<int:product_id>/', views.edit_product, name='edit-product'),
    path('delete-product/<int:product_id>/', views.delete_product, name='delete-product'),
    path('view-users/', views.view_users, name='view-users'),
    path('view-reports/', views.view_reports, name='view-reports'),
    path('manage-ingredients/', views.manage_ingredients, name='manage-ingredients'),
    path('add-ingredient/', views.add_ingredient, name='add-ingredient'),
    path('edit-ingredient/<int:ingredient_id>/', views.edit_ingredient, name='edit-ingredient'),
    path('delete-ingredient/<int:ingredient_id>/', views.delete_ingredient, name='delete-ingredient'),
    path('manage-users/delete/<int:user_id>/', views.admin_delete_user, name='admin-delete-user'),
    
    

    # ===== SKINCARE ANALYZER =====
    path('skincare-analyzer/', views.skincare_analyzer, name='skincare-analyzer'),
    path('skin-report/<int:report_id>/', views.skin_report_detail, name='skin-report-detail'),
    path('skin-reports/', views.skin_report_history, name='skin-report-history'),
    path('skin-profile/', views.skin_profile_setup, name='skin-profile-setup'),
    path('skin-report-delete/<int:report_id>/', views.skin_report_delete, name='skin-report-delete'),

    path('dashboard/skin-bulk-delete/', views.admin_skin_bulk_delete, name='admin-skin-bulk-delete'),

    # ===== API =====
    path('api/ingredient-search/', views.ingredient_search_api, name='ingredient-search-api'),
    path('ingredient/<str:ingredient_name>/info/', views.ingredient_scientific_info, name='ingredient-scientific-info'),



    path('admin-skin-delete-report-permanent/<int:report_id>/',  views.admin_skin_delete_report_permanent,  name='admin-skin-permanent-delete'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)