import csv
import os
import boto3
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.utils.timezone import now
from django.conf import settings
from rest_framework import viewsets
from .models import Expense
from .serializers import ExpenseSerializer

# AWS S3 Client (Cloud9 IAM Role is used, so no need for access keys)
s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)

# ------------------------- REST API for Expenses -------------------------

class ExpenseViewSet(viewsets.ModelViewSet):
    """API for CRUD operations on Expense model"""
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer


# ------------------------- Homepage View -------------------------

def home_view(request):
    """Renders the homepage"""
    return render(request, "index.html")


# ------------------------- Upload Page View -------------------------

def upload_page(request):
    """Handles file upload to S3"""
    if request.method == "POST" and request.FILES.get('file'):
        file = request.FILES['file']

        try:
            # Upload file to S3 inside "uploads/" folder
            s3_client.upload_fileobj(
                file, 
                settings.AWS_STORAGE_BUCKET_NAME, 
                f"uploads/{file.name}",
                ExtraArgs={'ACL': 'public-read'}
            )

            # Construct the correct public URL
            file_url = f"{settings.AWS_S3_CUSTOM_DOMAIN}/uploads/{file.name}"

            return render(request, "upload.html", {"file_url": file_url})

        except Exception as e:
            return render(request, "upload.html", {"error": str(e)})

    return render(request, "upload.html")



# ------------------------- Process Expense Inputs and Save as CSV -------------------------

def process_inputs(request):
    """Handles user input, stores expenses in DB, and saves CSV in S3."""
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        currency = request.POST.get("currency")

        # Fetch multiple inputs
        amounts = request.POST.getlist("amount[]")
        categories = request.POST.getlist("category[]")
        transaction_types = request.POST.getlist("transaction_type[]")
        payment_methods = request.POST.getlist("payment_method[]")

        # Generate a CSV filename
        filename = f"expenses_{user_id}_{now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join("/tmp", filename)  # Save locally first

        # Save to DB & Write CSV
        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["User ID", "Currency", "Amount", "Category", "Transaction Type", "Payment Method", "Timestamp"])

            for i in range(len(amounts)):
                Expense.objects.create(
                    user_id=user_id,
                    transaction_id=f"txn_{now().strftime('%Y%m%d%H%M%S')}_{i}",
                    amount=amounts[i],
                    currency=currency,
                    transaction_type=transaction_types[i],
                    category=categories[i],
                    timestamp=now(),
                    payment_method=payment_methods[i],
                )
                writer.writerow([user_id, currency, amounts[i], categories[i], transaction_types[i], payment_methods[i], now()])

        # Upload CSV to S3
        s3_client.upload_file(file_path, settings.AWS_STORAGE_BUCKET_NAME, f"uploads/{filename}")

        # Generate S3 File URL
        file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/uploads/{filename}"

        return HttpResponse(f"CSV Uploaded to S3: <a href='{file_url}'>{file_url}</a>")

    return JsonResponse({"error": "Invalid request method."}, status=400)
