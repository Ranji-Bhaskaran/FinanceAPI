""" urls.py"""
from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.home_view, name='home'),
    path('upload/', views.upload_page, name='upload_page'),
    path('process-inputs/', views.process_inputs, name='process-inputs'),
    path('get_detailed_insights/', views.get_detailed_insights, name='get_detailed_insights'),
    path('send-reminder/', views.send_reminder, name='send_reminder'),
    path("savings-plan/", views.savings_plan_page, name="savings_plan_page"),
    path("get-savings-plan/", views.get_savings_plan, name="get_savings_plan")

]
