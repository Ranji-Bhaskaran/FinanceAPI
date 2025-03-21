"""views.py"""
import csv
import os
import boto3
import json
import io
import base64
import requests
import pandas as pd
import matplotlib.pyplot as plt
from django.shortcuts import render
from django.http import JsonResponse
from django.utils.timezone import now
from django.conf import settings
from rest_framework import viewsets
from .models import Expense
from .serializers import ExpenseSerializer
from django.views.decorators.csrf import csrf_exempt
from twilio.rest import Client

# AWS S3 Client (IAM Role-based access)
s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)

# ------------------------- REST API for Expenses -------------------------

class ExpenseViewSet(viewsets.ModelViewSet):
    """API for CRUD operations on Expense model"""
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

# ------------------------- Homepage View -------------------------

def home_view(request):
    """Renders the homepage view"""
    return render(request, "index.html")

# ------------------------- Upload CSV to S3 -------------------------

def upload_page(request):
    """Handles file upload and saves to S3"""
    if request.method == "POST" and request.FILES.get('file'):
        file = request.FILES['file']
        file_key = f"upload/{file.name}"
        try:
            s3_client.upload_fileobj(
                file,
                settings.AWS_STORAGE_BUCKET_NAME,
                file_key,
                ExtraArgs={'ACL': 'public-read'})
            file_url = f"{settings.AWS_S3_CUSTOM_DOMAIN}/{file_key}"
            return render(request, "upload.html", {"file_url": file_url})
        except Exception as e:
            return render(request, "upload.html", {"error": str(e)})
    return render(request, "upload.html")

# ------------------------- Analyze Expenses from CSV -------------------------

def analyze_expenses(file_path):
    """Analyzes expenses from the uploaded CSV and generates a report"""
    try:
        df = pd.read_csv(file_path)
        df["Amount"] = pd.to_numeric(df["Converted Amount (EUR)"], errors="coerce")

        total_income = df[df["Transaction Type"] == "Income"]["Amount"].sum()
        total_expense = df[df["Transaction Type"] == "Expense"]["Amount"].sum()
        balance = total_income - total_expense
        category_expenses = df[df["Transaction Type"] == "Expense"].groupby("Category")["Amount"].sum()

        plt.figure(figsize=(6, 4))
        category_expenses.plot(kind="bar", color="skyblue")
        plt.title("Expense Distribution by Category")
        plt.xlabel("Category")
        plt.ylabel("Amount Spent")
        plt.xticks(rotation=45)

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode("utf-8")
        plt.close()

        return {
            "total_income": total_income,
            "total_expense": total_expense,
            "balance": balance,
            "status": "Saved" if balance >= 0 else "Overspent",
            "chart": image_base64,
            "category_expenses": category_expenses.to_dict()
        }
    except Exception as e:
        return {"error": str(e)}

# ------------------------- Get Detailed Insights from API -------------------------

@csrf_exempt
def get_detailed_insights(request):
    """Handles the AJAX request to get detailed insights from the external API."""
    if request.method == "POST":
        try:
            # Extract data from the AJAX request
            data = json.loads(request.body)
            total_expense = data.get("total_expense")
            target_expense = data.get("target_expense")
            category_expenses = data.get("category_expenses")
            
            api_url = "https://iuro44novi.execute-api.eu-west-1.amazonaws.com/dev/analyze-expenses"
            payload = {
                "total_amount_spent": total_expense,
                "total_amount_target": target_expense,
                "expenses": [{"category": cat, "amount": amt} for cat, amt in category_expenses.items()]
            }
            headers = {"Content-Type": "application/json"}

            # Make the API request
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            response_data = response.json()
            return JsonResponse(response_data)
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method."}, status=400)


# ------------------------- Process Expense Inputs & Store CSV -------------------------

def process_inputs(request):
    """Process expense inputs, generate CSV, and upload to S3"""
    if request.method == "POST":
        try:
            user_id = request.POST.get("user_id")
            currency = request.POST.get("currency", "EUR")
            amounts = request.POST.getlist("amount[]")
            categories = request.POST.getlist("category[]")
            transaction_types = request.POST.getlist("transaction_type[]")
            payment_methods = request.POST.getlist("payment_method[]")
            
            filename = f"expenses_{user_id}_{now().strftime('%Y%m%d_%H%M%S')}.csv"
            file_path = os.path.join("/tmp", filename)

            with open(file_path, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["User ID", "Original Currency", "Original Amount", "Converted Amount (EUR)", "Category", "Transaction Type", "Payment Method", "Timestamp"])
                
                for i in range(len(amounts)):
                    original_amount = float(amounts[i])
                    writer.writerow([user_id, currency, original_amount, original_amount, categories[i], transaction_types[i], payment_methods[i], now()])

            analysis = analyze_expenses(file_path)
            s3_client.upload_file(file_path, settings.AWS_STORAGE_BUCKET_NAME, f"upload/{filename}")
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/upload/{filename}"

            return render(request, "analysis.html", {"analysis": analysis, "file_url": file_url})
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method."}, status=400)

def send_reminder(request):
    """Sends a reminder message via Twilio API"""
    try:
        # Twilio credentials
        account_sid = settings.TWILIO_ACCOUNT_SID
        auth_token = settings.TWILIO_AUTH_TOKEN
        client = Client(account_sid, auth_token)

        message = client.messages.create(
            body="Reminder: Check your recent expenses and budget!",
            from_=settings.TWILIO_PHONE_NUMBER,
            to=settings.MY_PHONE_NUMBER
        )
        return JsonResponse({"message": "Reminder sent successfully!"})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)