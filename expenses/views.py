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

class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer

def home_view(request):
    return render(request, "index.html")

def upload_page(request):
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

def analyze_expenses(file_path):
    try:
        if not file_path or not os.path.exists(file_path):
            return {"error": "File path is invalid or does not exist."}

        df = pd.read_csv(file_path)
        if "Converted Amount (EUR)" not in df.columns:
            return {"error": "Missing 'Converted Amount (EUR)' column in CSV."}

        df["Amount"] = pd.to_numeric(df["Converted Amount (EUR)"], errors="coerce")
        df.dropna(subset=["Amount"], inplace=True)

        total_income = df[df["Transaction Type"] == "Income"]["Amount"].sum()
        total_expense = df[df["Transaction Type"] == "Expense"]["Amount"].sum()
        balance = total_income - total_expense
        category_expenses = df[df["Transaction Type"] == "Expense"].groupby("Category")["Amount"].sum()

        image_base64 = ""
        if not category_expenses.empty:
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

@csrf_exempt
def get_detailed_insights(request):
    if request.method == "POST":
        try:
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

            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            response_data = response.json()
            return JsonResponse(response_data)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=400)

def convert_currency(amount, from_currency):
    try:
        api_url = "https://2430zel9za.execute-api.eu-west-1.amazonaws.com/prod/convert"
        payload = {
            "amount": amount,
            "from_currency": from_currency,
            "to_currency": "EUR"
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        response_data = response.json()
        return response_data.get("converted_amount", amount)
    except Exception:
        return amount

def process_inputs(request):
    """Process expense inputs, generate CSV, and upload to S3"""
    if request.method == "POST":
        try:
            user_id = request.POST.get("user_id", "").strip()
            currency = request.POST.get("currency", "EUR").strip()

            amounts = request.POST.getlist("amount[]")
            categories = request.POST.getlist("category[]")
            transaction_types = request.POST.getlist("transaction_type[]")
            payment_methods = request.POST.getlist("payment_method[]")

            # Sanity checks
            if not user_id or not currency or not amounts:
                return JsonResponse({"error": "Missing required fields."}, status=400)

            if not (len(amounts) == len(categories) == len(transaction_types) == len(payment_methods)):
                return JsonResponse({"error": "Mismatched input lengths."}, status=400)

            filename = f"expenses_{user_id}_{now().strftime('%Y%m%d_%H%M%S')}.csv"
            file_path = os.path.join("/tmp", filename)

            with open(file_path, "w", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["User ID", "Original Currency", "Original Amount", "Converted Amount (EUR)", "Category", "Transaction Type", "Payment Method", "Timestamp"])
                
                for i in range(len(amounts)):
                    try:
                        original_amount = float(amounts[i])
                        converted_amount = convert_currency(original_amount, currency)
                        writer.writerow([user_id, currency, original_amount, converted_amount, categories[i], transaction_types[i], payment_methods[i], now()])
                    except Exception as row_error:
                        continue  # skip invalid rows safely

            analysis = analyze_expenses(file_path)
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/upload/{filename}"

            return render(request, "analysis.html", {"analysis": analysis, "file_url": file_url})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=400)


def send_reminder(request):
    if request.method == "POST":
        try:
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
    return JsonResponse({"error": "Invalid request method."}, status=400)
