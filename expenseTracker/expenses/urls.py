""" urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.home_view, name='home'),
    path('upload/', views.upload_page, name='upload'),
    path('process-inputs/', views.process_inputs, name='process-inputs'),
    path('get_detailed_insights/', views.get_detailed_insights, name='get_detailed_insights'),
    path('send-reminder/', views.send_reminder, name='send_reminder')
]
