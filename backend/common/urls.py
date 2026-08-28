from django.urls import path
from common.views import CommonCodeListView

urlpatterns = [
    path('codes/', CommonCodeListView.as_view(), name='common-code-list'),
]