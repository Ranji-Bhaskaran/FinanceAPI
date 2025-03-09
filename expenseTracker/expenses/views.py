import csv
import os
import boto3
import json
import io
import base64
import requests
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
        print("CSV Loaded Data:\n", df.head())  # Debugging Step

        df["Amount"] = pd.to_numeric(df["Converted Amount (EUR)"], errors="coerce")

        total_income = df[df["Transaction Type"] == "Income"]["Amount"].sum()
        total_expense = df[df["Transaction Type"] == "Expense"]["Amount"].sum()
        balance = total_income - total_expense

        print(f"Total Income: {total_income}, Total Expense: {total_expense}, Balance: {balance}")  # Debugging Step

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
        print(f"Error in analyze_expenses: {e}")  # Debugging Step
        return {"error": str(e)}


# ------------------------- Process Expense Inputs & Store CSV -------------------------

def convert_currency(amount, from_currency, to_currency="EUR"):
    """Calls external API to convert currency."""
    api_url = "https://2430zel9za.execute-api.eu-west-1.amazonaws.com/prod/convert"
    payload = {"amount": amount, "from_currency": from_currency, "to_currency": to_currency}
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        return response_data.get("converted_amount", amount)  # Default to original if API fails
    except Exception as e:
        print(f"Currency Conversion Error: {e}")
        return amount  # Return original amount in case of failure

def process_inputs(request):
    """Processes user inputs, saves data in DB, converts all currencies to EUR, analyzes CSV, and uploads to S3."""
    if request.method == "POST":
        try:
            user_id = request.POST.get("user_id")
            currency = request.POST.get("currency", "EUR")  # Default to EUR if missing
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
                    converted_amount = convert_currency(original_amount, currency, "EUR")  # Convert all to EUR

                    Expense.objects.create(
                        user_id=user_id,
                        transaction_id=f"txn_{now().strftime('%Y%m%d%H%M%S')}_{i}",
                        amount=converted_amount,  # Store only the converted amount in the DB
                        currency="EUR",  # Default currency to EUR in DB
                        transaction_type=transaction_types[i],
                        category=categories[i],
                        timestamp=now(),
                        payment_method=payment_methods[i],
                    )
                    writer.writerow([user_id, currency, original_amount, converted_amount, categories[i], transaction_types[i], payment_methods[i], now()])

            analysis = analyze_expenses(file_path)
            s3_client.upload_file(file_path, settings.AWS_STORAGE_BUCKET_NAME, f"upload/{filename}")
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/upload/{filename}"

            return render(request, "analysis.html", {"analysis": analysis, "file_url": file_url})
        
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)
    
    return JsonResponse({"error": "Invalid request method."}, status=400)

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
