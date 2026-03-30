"""
URL configuration for necroporra project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path

from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Django template views
    path('', views.landing_page_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('pools/create/', views.create_pool_view, name='create_pool'),
    path('settings/', views.user_settings_view, name='user_settings'),
    path('settings/change-password/', views.change_password_view, name='change_password'),
    path('pools/<str:slug>/', views.pool_detail_view, name='pool_detail'),
    path('join/<str:slug>/<str:invitation>/', views.join_pool_invite_view, name='join_pool_invite'),
    
    # API endpoints (for AJAX interactions)
    path('api/pools/<str:slug>/join/', views.join_pool_api, name='api_join_pool'),
    path('api/pools/<str:slug>/add_celebrity/', views.add_celebrity_to_pool_api, name='api_add_celebrity'),
    path('api/pools/<str:slug>/user-picks/', views.get_user_picks_api, name='api_user_picks'),
    path('api/pools/<str:slug>/predictions/<int:prediction_id>/delete/', views.delete_prediction_api, name='api_delete_prediction'),
    path('api/celebrities/search_wikidata/', views.search_wikidata_api, name='api_search_wikidata'),

    # Pool admin panel
    path('pools/<str:slug>/admin/', views.pool_admin_view, name='pool_admin'),
    path('api/pools/<str:slug>/transfer-admin/', views.transfer_admin_api, name='api_transfer_admin'),
    path('api/pools/<str:slug>/remove-member/', views.remove_member_api, name='api_remove_member'),
    path('api/pools/<str:slug>/delete/', views.delete_pool_api, name='api_delete_pool'),
    path('api/pools/<str:slug>/lock-now/', views.lock_pool_api, name='api_lock_pool'),
    path('api/pools/<str:slug>/regenerate-invite/', views.regenerate_invitation_api, name='api_regenerate_invite'),
    path('api/pools/<str:slug>/toggle-member-invite-links/', views.toggle_member_invite_links_api, name='api_toggle_member_invite_links'),
    path('api/pools/<str:slug>/toggle-visibility/', views.toggle_pool_visibility_api, name='api_toggle_pool_visibility'),
    path('api/pools/<str:slug>/mark-dead/', views.mark_celebrity_dead_api, name='api_mark_dead'),

    # User settings API
    path('api/settings/leave-pool/', views.leave_pool_api, name='api_leave_pool'),
    path('api/settings/delete-account/', views.delete_account_api, name='api_delete_account'),
]
