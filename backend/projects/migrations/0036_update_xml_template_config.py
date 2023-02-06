# Generated by Django 3.2.16 on 2023-02-03 03:09

from django.db import migrations
from projects.registry_helper import ProjectRegistry
from projects.models import Project


def update_xml_template_config(apps, schema_editor):
    projects_dict = ProjectRegistry.get_instance().project_types

    projects = Project.objects.all()

    projects_list = []
    for project in projects:
        setattr(
            project,
            "label_config",
            projects_dict[project.project_type]["label_studio_jsx_payload"],
        )
        projects_list.append(project)
    Project.objects.bulk_update(projects_list, ["label_config"], 512)


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0035_alter_project_project_type"),
    ]

    operations = [
        migrations.RunPython(update_xml_template_config),
    ]
