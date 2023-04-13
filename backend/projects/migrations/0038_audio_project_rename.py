# Generated by Django 3.2.14 on 2023-02-17 15:32

from django.db import migrations
from projects.models import Project


def audio_proj_rename(apps, schema_editor):
    projects = Project.objects.filter(
        project_type="SingleSpeakerAudioTranscriptionEditing"
    )
    projects_list = []
    for project in projects:
        setattr(project, "project_type", "AudioTranscription")
        projects_list.append(project)
    Project.objects.bulk_update(projects_list, ["project_type"], 512)


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0037_alter_project_project_type"),
    ]

    operations = [migrations.RunPython(audio_proj_rename)]