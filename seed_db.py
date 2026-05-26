import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
os.environ['USE_SQLITE'] = 'true'
django.setup()

from apps.organizations.models.tenant import Tenant, TenantSettings, Branch
from apps.accounts.models.user import User, Role

def seed():
    print("Seeding database...")
    # 1. Create Tenant
    tenant, created = Tenant.objects.get_or_create(
        subdomain="greenfield",
        defaults={
            "name": "Greenfield Academy",
            "institution_type": "school",
            "status": "active"
        }
    )
    if created:
        print(f"Created Tenant: {tenant}")
    else:
        print(f"Tenant already exists: {tenant}")

    # 2. Create Branch
    branch, created = Branch.objects.get_or_create(
        tenant=tenant,
        name="Main Campus",
        defaults={"code": "MC"}
    )
    if created:
        print(f"Created Branch: {branch}")

    # 3. Create TenantSettings
    settings, created = TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults={
            "student_id_label": "Roll Number",
            "faculty_id_label": "Employee ID"
        }
    )
    if created:
        print(f"Created Tenant Settings: {settings}")

    # 4. Create Admin User
    admin, created = User.objects.get_or_create(
        phone="+919876543210",
        role=Role.ADMIN,
        tenant=tenant,
        defaults={
            "first_name": "Greenfield",
            "last_name": "Admin",
            "branch": branch,
            "must_change_password": False,
            "is_active": True
        }
    )
    if created or admin.check_password("Password123!") is False:
        admin.set_password("Password123!")
        admin.save()
        print(f"Set admin user password. Log in using Phone: +919876543210 / Pass: Password123! / Role: Admin")

    # 5. Create Student User
    student, created = User.objects.get_or_create(
        custom_login_id="STU-001",
        role=Role.STUDENT,
        tenant=tenant,
        defaults={
            "first_name": "Rahul",
            "last_name": "Sharma",
            "branch": branch,
            "must_change_password": False,
            "is_active": True
        }
    )
    if created or student.check_password("Password123!") is False:
        student.set_password("Password123!")
        student.save()
        print(f"Set student user password. Log in using ID: STU-001 / Pass: Password123! / Role: Student")

    # 6. Create Faculty User
    faculty, created = User.objects.get_or_create(
        custom_login_id="FAC-001",
        role=Role.FACULTY,
        tenant=tenant,
        defaults={
            "first_name": "Priya",
            "last_name": "Patel",
            "branch": branch,
            "must_change_password": False,
            "is_active": True
        }
    )
    if created or faculty.check_password("Password123!") is False:
        faculty.set_password("Password123!")
        faculty.save()
        print(f"Set faculty user password. Log in using ID: FAC-001 / Pass: Password123! / Role: Faculty")

    print("Seeding completed successfully!")

if __name__ == "__main__":
    seed()
