#dashboard/urls.py

from django.urls import path
from dashboard.views import DashboardOverviewView, DashboardAnalyticsView
from dashboard.system_logs import DashboardSystemLogsView

app_name = 'dashboard'

urlpatterns = [
    path('system-logs/', DashboardSystemLogsView.as_view(), name='system-logs'),
    # GET /api/dashboard/overview/
    path('overview/', DashboardOverviewView.as_view(), name='overview'),
    
    # GET /api/dashboard/analytics/
    path('analytics/', DashboardAnalyticsView.as_view(), name='analytics'),
]