"""serializers.py"""
from rest_framework import serializers
from .models import Expense

class ExpenseSerializer(serializers.ModelSerializer):
    """class"""
    class Meta:
        """class meta"""
        model = Expense
        fields = '__all__'
