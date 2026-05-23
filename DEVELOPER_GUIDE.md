# EduOS Backend — Developer Guide

Welcome to the EduOS backend! This document outlines our architectural rules and explains *where* code belongs and *why*. Please read this carefully before writing any code.

## 🏛️ Architecture Overview

We use a **Domain-Driven Design** with a **"Thin View, Fat Service"** architecture. 

Instead of dumping everything into Django's `views.py` or `models.py`, we strictly segregate responsibilities. This makes the codebase highly reusable, easy to test, and scalable.

---

## 📂 Project Structure

Our application logic is divided into **Domains** (Apps). 
Example domains: `accounts`, `admissions`, `fees`, `academics`.

Inside every app, you will see this structure:
```text
apps/<app>/
├── models/           # Defines DB tables.
├── serializers/      # Validates incoming/outgoing JSON.
├── views/            # Handles HTTP (Accepts request, returns response).
├── interactors/      # Handles Business Logic (Orchestration & Validation).
├── queries/          # Handles ALL Database Operations (Reads & Writes).
└── tests/            # Unit tests for the above.
```

There is also a special app:
*   `apps/integrations/adapters/` — Handles communication with the outside world (Razorpay, AWS S3, MSG91).

---

## 🚦 The Rules of Segregation

### 1. Views (`views/`)
**What it does:** Handles the HTTP layer. 
**The Rule:** Views must be incredibly thin. A view should strictly only do three things:
1. Check permissions.
2. Validate incoming JSON data using a Serializer.
3. Call an **Interactor** or **Query** and return an HTTP response.
**Never do this:** Do not write ORM queries (`Model.objects.filter(...)`) or business logic in a view.

**Example:**
```python
# GOOD VIEW
class EnrollStudentView(APIView):
    def post(self, request):
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Call the interactor. The view knows NOTHING about how enrollment works.
        student = enroll_student_interactor(**serializer.validated_data)
        
        return Response({"status": "Success"}, status=201)
```

### 2. Interactors (`interactors/`)
**What it does:** Handles Business Logic, Data Validation, and orchestrates workflows.
**The Rule:** An Interactor should **never** contain raw ORM code (`Model.objects...`). If it needs to read or write to the database, it must call a function from `queries/`.

**Example:**
```python
# apps/admissions/interactors/enrollment.py
from apps.admissions.queries.student import save_student

def enroll_student_interactor(user_id, course_id):
    # 1. Business logic
    if not course_is_open(course_id):
        raise ValidationError("Course is full.")
        
    # 2. Database mutation (Delegated to Queries layer)
    student = save_student(user_id, course_id)
    
    # 3. Workflow trigger
    send_welcome_email(student.email)
    return student
```

### 3. Queries (`queries/`)
**What it does:** Handles **ALL** Database Operations (both Reads and Writes).
**The Rule:** This is the *only* place in your app where Django ORM code (`Model.objects...`) is allowed. All `.filter()`, `.create()`, `.update()`, and `.select_related()` logic goes here.

**Example:**
```python
# apps/fees/queries/invoice.py

# A Read Query
def get_unpaid_invoices_for_student(student_id):
    return FeeInvoice.objects.filter(
        student_id=student_id, 
        status='UNPAID'
    ).select_related('fee_structure')

# A Write Query
def mark_invoice_as_paid(invoice):
    invoice.status = 'PAID'
    invoice.save(update_fields=['status'])
    return invoice
```

### 4. Adapters (`apps/integrations/adapters/`)
**What it does:** Talks to 3rd-Party APIs (The Outside World).
**The Rule:** Never put raw SDK code (like `boto3` or `razorpay`) inside a service. Wrap it in an adapter. This protects our business logic if the 3rd-party API changes.

**Example:**
```python
# 1. The Adapter (apps/integrations/adapters/razorpay.py)
import razorpay
def create_payment_link(amount, currency="INR"):
    client = razorpay.Client(...)
    return client.payment_link.create({"amount": amount * 100})

# 2. The Interactor using the Adapter (apps/fees/interactors/payment.py)
from apps.integrations.adapters.razorpay import create_payment_link

def process_fee_payment(invoice):
    # The interactor doesn't know how Razorpay works, it just calls the adapter.
    link = create_payment_link(invoice.amount)
    return link
```

---

## 🤝 Inter-App Communication (How Apps Talk)

Apps need to share data and trigger actions in each other. 
**The Golden Rule:** Apps communicate by calling each other's **Interactors** and **Queries**. 

**Scenario:** The `admissions` app admits a student. It now needs to create a user account in the `accounts` app.

**How to do it:**
Import the `accounts` interactor directly into the `admissions` interactor.

```python
# apps/admissions/interactors/enrollment.py

# ✅ GOOD: Importing an external app's interactor
from apps.accounts.interactors.user import create_user_account

def finalize_admission(application):
    # Update admission status
    application.status = "ADMITTED"
    application.save()
    
    # Trigger the external app's interactor
    new_user = create_user_account(email=application.email, role="STUDENT")
    return new_user
```

**Where to put shared Utility functions?**
If a function is purely a generic utility (e.g., generating a random password, formatting a date) and does not belong to a specific business domain, put it in `apps/core/utils.py`.

---

## 📝 Summary Checklist for New Code

1. Am I getting HTTP parameters or validating JSON? 👉 **View / Serializer**
2. Am I modifying the database or running a business workflow? 👉 **Interactor**
3. Am I running a `Model.objects...` query (read or write)? 👉 **Query**
4. Am I making an HTTP request to AWS, MSG91, or Razorpay? 👉 **Adapter**
5. Does App A need to trigger something in App B? 👉 **App A's Interactor imports App B's Interactor.**
