from django.contrib import admin
from .models import Expense

# Customize the admin interface for Expense model
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user_id', 'transaction_id', 'amount', 'currency', 'transaction_type', 'category', 'timestamp', 'payment_method')  # Customize the columns to display
    search_fields = ('user_id', 'transaction_id', 'category', 'payment_method')  # Add search functionality for specified fields
    list_filter = ('transaction_type', 'category', 'currency', 'payment_method')  # Add filters based on fields
    ordering = ('-timestamp',)  # Order by timestamp in descending order
    date_hierarchy = 'timestamp'  # Add a date-based navigation for filtering

# Register Expense model with custom admin configuration
admin.site.register(Expense, ExpenseAdmin)
