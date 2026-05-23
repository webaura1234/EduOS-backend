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

**Architectural Rule:** You MUST use **Class-Based Views (CBVs)** exclusively (e.g., `APIView` or `ViewSet`). Function-Based Views (FBVs) are strictly prohibited for scalability and reusability reasons.

**Never do this:** Do not write ORM queries (`Model.objects.filter(...)`) or business logic in a view.

**Example:**
```python
# GOOD VIEW
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import EnrollmentSerializer
from apps.admissions.interactors.enrollment import EnrollStudentInteractor, EnrollmentDTO

class EnrollStudentView(APIView):
    def post(self, request):
        serializer = EnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Convert raw validated data into a strict DTO
        dto = EnrollmentDTO(**serializer.validated_data)
        
        # Call the interactor. The view knows NOTHING about how enrollment works.
        interactor = EnrollStudentInteractor()
        student = interactor.execute(dto)
        
        return Response({"status": "Success"}, status=201)
```

### 2. Interactors (`interactors/`)
**What it does:** Handles Business Logic, Data Validation, and orchestrates workflows.
**The Rules:** 
1. **Class-based:** Interactors MUST be class-based.
2. **Dependency Injection:** Inject Queries or Adapters via `__init__` for perfect test mocking.
3. **Data Transfer Objects (DTOs):** Never pass raw dicts into Interactors. Pass a strict Python `@dataclass`.
4. **No ORM Code:** Never write `Model.objects...` here.

**Example:**
```python
# apps/admissions/interactors/enrollment.py
from dataclasses import dataclass
from apps.admissions.queries.student import StudentQuery

@dataclass(frozen=True)
class EnrollmentDTO:
    user_id: str
    course_id: str

class EnrollStudentInteractor:
    def __init__(self, query_class=StudentQuery):
        # Dependency injection allows us to mock the DB entirely in tests
        self.query = query_class()

    def execute(self, dto: EnrollmentDTO):
        # 1. Business logic
        if not self.query.is_course_open(dto.course_id):
            raise ValidationError("Course is full.")
            
        # 2. Database mutation (Delegated to Queries layer)
        student = self.query.save_student(dto.user_id, dto.course_id)
        
        # 3. Workflow trigger
        send_welcome_email(student.email)
        return student
```

### 3. Queries (`queries/`)
**What it does:** Handles **ALL** Database Operations (both Reads and Writes).
**The Rule:** This is the *only* place in your app where Django ORM code (`Model.objects...`) is allowed. **Queries MUST be class-based.**

**Example:**
```python
# apps/fees/queries/invoice.py

class InvoiceQuery:
    # A Read Query
    def get_unpaid_invoices_for_student(self, student_id):
        return FeeInvoice.objects.filter(
            student_id=student_id, 
            status='UNPAID'
        ).select_related('fee_structure')

    # A Write Query
    def mark_invoice_as_paid(self, invoice):
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

class RazorpayAdapter:
    def __init__(self):
        self.client = razorpay.Client(...)

    def create_payment_link(self, amount, currency="INR"):
        return self.client.payment_link.create({"amount": amount * 100})

# 2. The Interactor using the Adapter (apps/fees/interactors/payment.py)
from apps.integrations.adapters.razorpay import RazorpayAdapter

class ProcessFeePaymentInteractor:
    def __init__(self, invoice):
        self.invoice = invoice
        self.adapter = RazorpayAdapter()

    def execute(self):
        # The interactor doesn't know how Razorpay works, it just calls the adapter.
        link = self.adapter.create_payment_link(self.invoice.amount)
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
from apps.accounts.interactors.user import CreateUserAccountInteractor

class FinalizeAdmissionInteractor:
    def __init__(self, application):
        self.application = application

    def execute(self):
        # Update admission status
        self.application.status = "ADMITTED"
        self.application.save()
        
        # Trigger the external app's interactor
        user_interactor = CreateUserAccountInteractor(
            email=self.application.email, 
            role="STUDENT"
        )
        return user_interactor.execute()
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
