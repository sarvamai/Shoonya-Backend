# Generated by Django 3.2.14 on 2023-11-22 16:24

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_auto_20231013_0926"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="notification",
            options={"ordering": ("-created_at",)},
        ),
        migrations.AlterField(
            model_name="notification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("publish_project", "Publish Project"),
                    ("task_reject", "Task Reject"),
                ],
                max_length=200,
            ),
        ),
    ]