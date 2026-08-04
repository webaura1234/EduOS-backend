"""Canonical student-import columns and aliases."""

from __future__ import annotations

CANONICAL_COLUMNS: list[dict] = [
    {
        "key": "admission_number",
        "label": "Admission Number",
        "required_create": True,
        "required_update": True,
        "aliases": ["admission_number", "admission no", "adm no", "adm_no", "roll number", "roll_no", "roll no"],
    },
    {
        "key": "first_name",
        "label": "First Name",
        "required_create": True,
        "required_update": False,
        "aliases": ["first_name", "first name", "firstname", "student first name"],
    },
    {
        "key": "last_name",
        "label": "Last Name",
        "required_create": False,
        "required_update": False,
        "aliases": ["last_name", "last name", "lastname", "surname"],
    },
    {
        "key": "date_of_birth",
        "label": "Date of Birth",
        "required_create": False,
        "required_update": False,
        "aliases": ["date_of_birth", "date of birth", "dob", "birth date", "birthdate"],
    },
    {
        "key": "gender",
        "label": "Gender",
        "required_create": False,
        "required_update": False,
        "aliases": ["gender", "sex"],
    },
    {
        "key": "class",
        "label": "Class",
        "required_create": True,
        "required_update": False,
        "aliases": ["class", "grade", "course", "class name", "class_name"],
    },
    {
        "key": "section",
        "label": "Section",
        "required_create": True,
        "required_update": False,
        "aliases": ["section", "sec", "batch", "section name"],
    },
    {
        "key": "student_mobile",
        "label": "Student Mobile",
        "required_create": False,
        "required_update": False,
        "aliases": ["student_mobile", "student phone", "student mobile", "mobile", "phone"],
    },
    {
        "key": "student_email",
        "label": "Student Email",
        "required_create": False,
        "required_update": False,
        "aliases": ["student_email", "student email", "email"],
    },
    {
        "key": "parent_name",
        "label": "Parent Name",
        "required_create": True,
        "required_update": False,
        "aliases": ["parent_name", "parent name", "guardian name", "father name", "mother name"],
    },
    {
        "key": "parent_mobile",
        "label": "Parent Mobile",
        "required_create": True,
        "required_update": False,
        "aliases": ["parent_mobile", "parent phone", "parent mobile", "guardian phone", "guardian mobile"],
    },
    {
        "key": "parent_email",
        "label": "Parent Email",
        "required_create": False,
        "required_update": False,
        "aliases": ["parent_email", "parent email", "guardian email"],
    },
    {
        "key": "parent_relationship",
        "label": "Parent Relationship",
        "required_create": False,
        "required_update": False,
        "aliases": ["parent_relationship", "relationship", "guardian relationship"],
    },
    {
        "key": "fee_structure",
        "label": "Fee Structure",
        "required_create": False,
        "required_update": False,
        "aliases": ["fee_structure", "fee structure", "fee plan", "fees"],
    },
    {
        "key": "sibling_admission_no",
        "label": "Sibling Admission No",
        "required_create": False,
        "required_update": False,
        "aliases": ["sibling_admission_no", "sibling admission no", "sibling roll"],
    },
]

CANONICAL_KEYS = [c["key"] for c in CANONICAL_COLUMNS]

SAMPLE_ROWS = [
    {
        "admission_number": "ADM-1001",
        "first_name": "Aarav",
        "last_name": "Sharma",
        "date_of_birth": "2015-04-12",
        "gender": "male",
        "class": "Class 5",
        "section": "A",
        "student_mobile": "",
        "student_email": "",
        "parent_name": "Ravi Sharma",
        "parent_mobile": "+919876543210",
        "parent_email": "ravi@example.com",
        "parent_relationship": "father",
        "fee_structure": "",
        "sibling_admission_no": "",
    },
    {
        "admission_number": "ADM-1002",
        "first_name": "Diya",
        "last_name": "Patel",
        "date_of_birth": "2015-08-03",
        "gender": "female",
        "class": "Class 5",
        "section": "A",
        "student_mobile": "",
        "student_email": "",
        "parent_name": "Meera Patel",
        "parent_mobile": "+919876543211",
        "parent_email": "",
        "parent_relationship": "mother",
        "fee_structure": "",
        "sibling_admission_no": "",
    },
]

INSTRUCTIONS = (
    "Student Import Template\n"
    "1. Fill one row per student.\n"
    "2. admission_number must be unique within the school (becomes login / roll id).\n"
    "3. class + section must match an existing class & section for the selected academic year.\n"
    "4. Dates must be YYYY-MM-DD. Gender: male / female / other.\n"
    "5. parent_name and parent_mobile are required when creating new students.\n"
    "6. fee_structure is optional; if set, it must match a published fee structure name.\n"
    "7. Do not change the header row names if you want auto-mapping to work.\n"
)
