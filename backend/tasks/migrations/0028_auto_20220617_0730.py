# Generated by Django 3.1.14 on 2022-06-17 07:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0027_alter_annotation_notes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tasklock',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
    ]
