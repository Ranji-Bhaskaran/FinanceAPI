"""admin.py"""
from django.contrib import admin
from .models import Expense

# Customize the admin interface for Expense model
class ExpenseAdmin(admin.ModelAdmin):
    """ class for expense """
    list_display = (
        'user_id',
        'transaction_id',
        'amount',
        'currency',
        'transaction_type',
        'category',
        'timestamp',
        'payment_method')
    search_fields = ('user_id', 'transaction_id', 'category', 'payment_method')
    list_filter = ('transaction_type', 'category', 'currency', 'payment_method')
    ordering = ('-timestamp',)
    date_hierarchy = 'timestamp'

# Register Expense model with custom admin configuration
admin.site.register(Expense, ExpenseAdmin)
