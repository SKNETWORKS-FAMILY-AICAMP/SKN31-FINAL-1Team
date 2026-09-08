#dashboard/urls.py

from django.urls import path
from dashboard.views import DashboardOverviewView, DashboardAnalyticsView

app_name = 'dashboard'

urlpatterns = [
    # GET /api/dashboard/overview/
    path('overview/', DashboardOverviewView.as_view(), name='overview'),
    
    # GET /api/dashboard/analytics/
    path('analytics/', DashboardAnalyticsView.as_view(), name='analytics'),
]