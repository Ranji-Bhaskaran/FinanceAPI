from django.urls import path
from . import views

urlpatterns = [
    # Pages
    path('', views.home_view, name='home'),
    path('upload/', views.upload_page, name='upload'),
    path('process-inputs/', views.process_inputs, name='process-inputs')
]