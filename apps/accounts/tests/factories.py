import factory
from factory.django import DjangoModelFactory

from apps.accounts.models.user import User, Role
from apps.accounts.models.token import RefreshToken, OTPRecord, InviteToken
from apps.accounts.models.security import LoginAttempt
from apps.organizations.tests.factories import TenantFactory, BranchFactory


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    role = Role.STUDENT
    phone = factory.Sequence(lambda n: f"+9198765{n:05d}")
    custom_login_id = factory.Sequence(lambda n: f"STUDENT-{n}")
    tenant = factory.SubFactory(TenantFactory)
    branch = factory.SubFactory(BranchFactory, tenant=factory.SelfAttribute("..tenant"))
    is_active = True
    must_change_password = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        """Override to handle password hashing properly."""
        password = kwargs.pop("password", "TestPass123!")
        user = super()._create(model_class, *args, **kwargs)
        if password:
            user.set_password(password)
            user.save()
        return user


class RefreshTokenFactory(DjangoModelFactory):
    class Meta:
        model = RefreshToken

    user = factory.SubFactory(UserFactory)
    token = factory.Sequence(lambda n: f"fake-refresh-token-{n}")
    is_revoked = False


class OTPRecordFactory(DjangoModelFactory):
    class Meta:
        model = OTPRecord

    user = factory.SubFactory(UserFactory)
    otp_hash = "hashed_otp_placeholder"
    phone = factory.LazyAttribute(lambda o: o.user.phone)
    is_used = False


class InviteTokenFactory(DjangoModelFactory):
    class Meta:
        model = InviteToken

    user = factory.SubFactory(UserFactory)
    is_used = False
    sent_to_phone = factory.LazyAttribute(lambda o: o.user.phone or "")


class LoginAttemptFactory(DjangoModelFactory):
    class Meta:
        model = LoginAttempt

    identifier = factory.Sequence(lambda n: f"user-{n}")
    tenant = factory.SubFactory(TenantFactory)
    was_successful = False
    failure_reason = "wrong_password"
