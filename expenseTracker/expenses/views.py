import csv
import os
import boto3
import json
import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.utils.timezone import now
from django.conf import settings
from rest_framework import viewsets
from .models import Expense
from .serializers import ExpenseSerializer

# AWS S3 Client (IAM Role-based access)
s3_client = boto3.client('s3', region_name=settings.AWS_S3_REGION_NAME)
API_GATEWAY_URL = "https://iuro44novi.execute-api.eu-west-1.amazonaws.com/dev/analyze-expenses"

# ------------------------- REST API for Expenses -------------------------

class ExpenseViewSet(viewsets.ModelViewSet):
    """API for CRUD operations on Expense model"""
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

# ------------------------- Homepage View -------------------------

def home_view(request):
    return render(request, "index.html")

# ------------------------- Upload CSV to S3 -------------------------

def upload_page(request):
    """Handles file upload to S3."""
    if request.method == "POST" and request.FILES.get('file'):
        file = request.FILES['file']
        file_key = f"upload/{file.name}"
        try:
            s3_client.upload_fileobj(file, settings.AWS_STORAGE_BUCKET_NAME, file_key, ExtraArgs={'ACL': 'public-read'})
            file_url = f"{settings.AWS_S3_CUSTOM_DOMAIN}/{file_key}"
            return render(request, "upload.html", {"file_url": file_url})
        except Exception as e:
            return render(request, "upload.html", {"error": str(e)})
    return render(request, "upload.html")

# ------------------------- Analyze Expenses from CSV -------------------------

def analyze_expenses(file_path):
    """Reads CSV, calculates totals, and generates graphs."""
    try:
        df = pd.read_csv(file_path)
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

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
            "chart": image_base64
        }
    except Exception as e:
        return {"error": str(e)}

# ------------------------- Process Expense Inputs & Store CSV -------------------------

def process_inputs(request):
    """Processes user inputs, saves data in DB, analyzes CSV, and uploads to S3."""
    if request.method == "POST":
        user_id = request.POST.get("user_id")
        currency = request.POST.get("currency")
        amounts = request.POST.getlist("amount[]")
        categories = request.POST.getlist("category[]")
        transaction_types = request.POST.getlist("transaction_type[]")
        payment_methods = request.POST.getlist("payment_method[]")
        
        filename = f"expenses_{user_id}_{now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join("/tmp", filename)

        with open(file_path, "w", newline="") as file:
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

        analysis = analyze_expenses(file_path)
        s3_client.upload_file(file_path, settings.AWS_STORAGE_BUCKET_NAME, f"upload/{filename}")
        file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/upload/{filename}"

        return render(request, "analysis.html", {"analysis": analysis, "file_url": file_url})

    return JsonResponse({"error": "Invalid request method."}, status=400)

# ------------------------- Retrieve Analysis Results -------------------------

def get_analysis(request, file_name):
    """Fetches analyzed expense insights from S3."""
    try:
        analysis_key = f"upload/{file_name}_analysis.json"
        response = s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=analysis_key)
        insights = json.loads(response['Body'].read().decode('utf-8'))
        return JsonResponse(insights)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# ------------------------- Display Analysis Page -------------------------

def display_analysis(request, file_name):
    """Renders an HTML page with expense insights."""
    try:
        analysis_key = f"upload/{file_name}_analysis.json"
        response = s3_client.get_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=analysis_key)
        insights = json.loads(response['Body'].read().decode('utf-8'))
        return render(request, "analysis.html", {"insights": insights})
    except Exception as e:
        return render(request, "analysis.html", {"error": str(e)})
