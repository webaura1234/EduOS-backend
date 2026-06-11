import factory
from factory.django import DjangoModelFactory

from apps.fees.models import FeeInvoice, FeeStructure, Payment, StudentFeeAssignment


class FeeStructureFactory(DjangoModelFactory):
    class Meta:
        model = FeeStructure

    name = factory.Sequence(lambda n: f"Structure {n}")
    components = factory.LazyFunction(lambda: [
        {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1},
    ])


class StudentFeeAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = StudentFeeAssignment


class FeeInvoiceFactory(DjangoModelFactory):
    class Meta:
        model = FeeInvoice

    total_paise = 5000000
    paid_paise = 0


class PaymentFactory(DjangoModelFactory):
    class Meta:
        model = Payment

    amount_paise = 5000000
    idempotency_key = factory.Sequence(lambda n: f"pay-key-{n}")
