"""apps.py"""
from django.apps import AppConfig


class ExpensesConfig(AppConfig):
    """class for expense config"""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'expenses'
