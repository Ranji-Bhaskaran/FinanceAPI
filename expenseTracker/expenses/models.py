""" models.py """
from django.db import models

class Expense(models.Model):
    """ class expense """
    user_id = models.CharField(max_length=50)
    transaction_id = models.CharField(max_length=50, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10)
    transaction_type = models.CharField(max_length=20)
    category = models.CharField(max_length=50)
    timestamp = models.DateTimeField()
    payment_method = models.CharField(max_length=50)

    def __str__(self):
        return f"{self.user_id} - {self.category} - {self.amount}"
