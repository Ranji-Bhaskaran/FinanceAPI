import csv
import os
import boto3
import json
import io
import base64
import random
import requests
import pandas as pd
import matplotlib.pyplot as plt
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.utils.timezone import now
from django.conf import settings
from rest_framework import viewsets
from .models import Expense
from .serializers import ExpenseSerializer
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from twilio.rest import Client

# AWS S3 Client (IAM Role-based access)
s3_client = boto3.client('s3', region_name="eu-west-1")

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
                file_key)
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

import tempfile  # add this at the top if not already imported

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

            # Filename and S3 Key
            filename = f"expenses_{user_id}_{now().strftime('%Y%m%d_%H%M%S')}.csv"
            s3_key = f"upload/{filename}"

            # Create temp CSV file
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, newline="") as temp_csv:
                writer = csv.writer(temp_csv)
                writer.writerow([
                    "User ID", "Original Currency", "Original Amount",
                    "Converted Amount (EUR)", "Category", "Transaction Type",
                    "Payment Method", "Timestamp"
                ])
                for i in range(len(amounts)):
                    try:
                        original_amount = float(amounts[i])
                        converted_amount = convert_currency(original_amount, currency)
                        writer.writerow([
                            user_id, currency, original_amount, converted_amount,
                            categories[i], transaction_types[i], payment_methods[i], now()
                        ])
                    except Exception as row_err:
                        continue  # skip invalid rows
                temp_csv_path = temp_csv.name  # capture the temp path

            # Upload to S3
            try:
                s3_client.upload_file(
                    temp_csv_path,
                    settings.AWS_STORAGE_BUCKET_NAME,
                    s3_key
                )
            except Exception as upload_error:
                return JsonResponse({"error": f"Failed to upload to S3: {upload_error}"}, status=500)

            # Analyze and return
            analysis = analyze_expenses(temp_csv_path)
            file_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"

            return render(request, "analysis.html", {
                "analysis": analysis,
                "file_url": file_url
            })

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method."}, status=400)

@never_cache
def savings_plan_page(request):
    if request.method == "POST":
        current_savings = request.POST.get("current_savings", "0.00")
    else:
        current_savings = "0.00"

    return render(request, "savingsplan.html", {
        "current_savings": current_savings,
        "quote": get_financial_quote()
    })


@csrf_exempt
@require_POST
@never_cache
def get_savings_plan(request):
    try:
        goal_amount = request.POST.get("goal_amount")
        current_savings = request.POST.get("current_savings")
        goal_date = request.POST.get("goal_date")

        if not goal_amount or not current_savings or not goal_date:
            return render(request, "savingsplan.html", {
                "error": "All fields are required.",
                "current_savings": current_savings,
                "quote": get_financial_quote()
            })

        api_url = "https://s5n43ij2al.execute-api.eu-west-1.amazonaws.com/prod/plan-savings"
        payload = {
            "goal_amount": float(goal_amount),
            "current_savings": float(current_savings),
            "goal_date": goal_date
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        plan_data = response.json()

        return render(request, "savingsplan.html", {
            "plan": plan_data,
            "current_savings": current_savings,
            "quote": get_financial_quote()
        })

    except Exception as e:
        return render(request, "savingsplan.html", {
            "error": str(e),
            "current_savings": request.POST.get("current_savings", "0.00"),
            "quote": get_financial_quote()
        })


def get_financial_quote():
    quotes = [
        "Start where you are. Use what you have. Do what you can. — Arthur Ashe",
        "Do not save what is left after spending, but spend what is left after saving. — Warren Buffett",
        "A budget is telling your money where to go instead of wondering where it went. — Dave Ramsey",
        "The goal isn't more money. The goal is living life on your terms. — Chris Brogan",
        "An investment in knowledge pays the best interest. — Benjamin Franklin"
    ]
    return random.choice(quotes)


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
