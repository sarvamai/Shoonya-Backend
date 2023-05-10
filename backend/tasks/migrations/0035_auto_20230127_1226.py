# Generated by Django 3.2.16 on 2023-01-27 12:26


from django.db import migrations, models
from django.db.models import Q
from tasks.models import Annotation, Task
from tasks.views import SentenceOperationViewSet
from tqdm import tqdm


class Migration(migrations.Migration):
    dependencies = [
        ("tasks", "0034_auto_20230127_1221"),
    ]
    operations = [
        migrations.AlterField(
            model_name="task",
            name="task_status",
            field=models.CharField(
                choices=[
                    ("incomplete", "incomplete"),
                    ("annotated", "annotated"),
                    ("reviewed", "reviewed"),
                    ("exported", "exported"),
                    ("freezed", "freezed"),
                ],
                default="incomplete",
                max_length=100,
                verbose_name="task_status",
            ),
        ),
    ]
