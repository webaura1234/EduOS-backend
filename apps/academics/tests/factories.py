import datetime
import factory
from factory.django import DjangoModelFactory

from apps.academics.models.calendar import AcademicYear
from apps.academics.models.structure import Batch, Course, Department
from apps.organizations.tests.factories import BranchFactory


class AcademicYearFactory(DjangoModelFactory):
    class Meta:
        model = AcademicYear

    branch = factory.SubFactory(BranchFactory)
    name = factory.Sequence(lambda n: f"202{n}-2{n+1}")
    start_date = factory.LazyFunction(lambda: datetime.date.today())
    end_date = factory.LazyFunction(lambda: datetime.date.today() + datetime.timedelta(days=365))
    is_current = False
    is_frozen = False


class DepartmentFactory(DjangoModelFactory):
    class Meta:
        model = Department

    branch = factory.SubFactory(BranchFactory)
    name = factory.Sequence(lambda n: f"Dept {n}")
    code = factory.Sequence(lambda n: f"D{n}")


class CourseFactory(DjangoModelFactory):
    class Meta:
        model = Course

    department = factory.SubFactory(DepartmentFactory)
    name = factory.Sequence(lambda n: f"Course {n}")
    code = factory.Sequence(lambda n: f"C{n}")


class BatchFactory(DjangoModelFactory):
    class Meta:
        model = Batch

    course = factory.SubFactory(CourseFactory)
    academic_year = factory.SubFactory(AcademicYearFactory, branch=factory.SelfAttribute("..course.department.branch"))
    name = factory.Sequence(lambda n: f"Section {n}")
    capacity = 40
