from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, permission_classes
from rest_framework.permissions import IsAuthenticated
from projects.serializers import ProjectSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from projects.models import Project, ANNOTATION_STAGE, REVIEW_STAGE, SUPERCHECK_STAGE
from users.models import User
from users.serializers import UserProfileSerializer
from tasks.models import Task
from organizations.models import Organization
from django.db.models import Q
from projects.utils import no_of_words
from tasks.models import (
    Annotation,
    ANNOTATOR_ANNOTATION,
    REVIEWER_ANNOTATION,
    SUPER_CHECKER_ANNOTATION,
)
from projects.utils import is_valid_date
from datetime import datetime, timezone, timedelta
import pandas as pd
from dateutil import relativedelta
import calendar
from users.serializers import UserFetchSerializer
from users.utils import get_role_name
from projects.utils import (
    minor_major_accepted_task,
    convert_seconds_to_hours,
    get_audio_project_types,
    get_audio_transcription_duration,
    get_audio_segments_count,
    calculate_word_error_rate_between_two_audio_transcription_annotation,
    get_translation_dataset_project_types,
    convert_hours_to_seconds,
)
from projects.views import ProjectViewSet

from .serializers import (
    UnAssignManagerSerializer,
    WorkspaceManagerSerializer,
    WorkspaceSerializer,
    WorkspaceNameSerializer,
)
from .models import Workspace
from .decorators import (
    workspace_is_archived,
    is_particular_workspace_manager,
    is_particular_organization_owner,
    is_organization_owner_or_workspace_manager,
    is_workspace_creator,
)
from .tasks import (
    send_user_reports_mail_ws,
    send_project_analysis_reports_mail_ws,
    send_user_analysis_reports_mail_ws,
)


# Create your views here.

EMAIL_VALIDATION_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


def get_task_count(proj_ids, status, annotator, return_count=True):
    annotated_tasks = Task.objects.filter(
        Q(project_id__in=proj_ids)
        & Q(task_status__in=status)
        & Q(annotation_users=annotator)
    )

    if return_count == True:
        annotated_tasks_count = annotated_tasks.count()
        return annotated_tasks_count
    else:
        return annotated_tasks


def get_task_count_project_analytics(proj_id, status_list, return_count=True):
    labeled_tasks = Task.objects.filter(project_id=proj_id, task_status__in=status_list)
    if return_count == True:
        labeled_tasks_count = labeled_tasks.count()
        return labeled_tasks_count
    else:
        return labeled_tasks


def get_annotated_tasks(proj_ids, annotator, status_list, start_date, end_date):
    annotated_tasks_objs = get_task_count(
        proj_ids, status_list, annotator, return_count=False
    )

    annotated_task_ids = list(annotated_tasks_objs.values_list("id", flat=True))
    annotated_labeled_tasks = Annotation.objects.filter(
        task_id__in=annotated_task_ids,
        annotation_type=ANNOTATOR_ANNOTATION,
        updated_at__range=[start_date, end_date],
        completed_by=annotator,
    )

    return annotated_labeled_tasks


def get_annotated_tasks_project_analytics(proj_id, status_list, start_date, end_date):
    labeled_tasks = get_task_count_project_analytics(
        proj_id, status_list, return_count=False
    )

    labeled_tasks_ids = list(labeled_tasks.values_list("id", flat=True))
    annotated_labeled_tasks = Annotation.objects.filter(
        task_id__in=labeled_tasks_ids,
        annotation_type=ANNOTATOR_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    return annotated_labeled_tasks


def get_supercheck_reports(proj_ids, userid, start_date, end_date, project_type=None):
    user = User.objects.get(id=userid)
    participation_type = user.participation_type
    participation_type = (
        "Full Time"
        if participation_type == 1
        else "Part Time"
        if participation_type == 2
        else "Contract Basis"
        if participation_type == 4
        else "N/A"
    )
    role = get_role_name(user.role)
    userName = user.username
    email = user.email

    superchecker_languages = user.languages

    total_tasks = Task.objects.filter(project_id__in=proj_ids, super_check_user=userid)

    total_task_count = total_tasks.count()

    validated_objs = Annotation.objects.filter(
        annotation_status="validated",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    validated_objs_count = validated_objs.count()

    validated_with_changes_objs = Annotation.objects.filter(
        annotation_status="validated_with_changes",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    validated_with_changes_objs_count = validated_with_changes_objs.count()

    unvalidated_objs = Annotation.objects.filter(
        annotation_status="unvalidated",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    unvalidated_objs_count = unvalidated_objs.count()

    rejected_objs = Annotation.objects.filter(
        annotation_status="rejected",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    rejected_objs_count = rejected_objs.count()

    skipped_objs = Annotation.objects.filter(
        annotation_status="skipped",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    skipped_objs_count = skipped_objs.count()

    draft_objs = Annotation.objects.filter(
        annotation_status="draft",
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    draft_objs_count = draft_objs.count()

    total_sup_annos = Annotation.objects.filter(
        task__project_id__in=proj_ids,
        task__super_check_user=userid,
        annotation_type=SUPER_CHECKER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    total_superchecked_annos = total_sup_annos.filter(task__task_status="super_checked")

    total_rejection_loop_value_list = [
        anno.task.revision_loop_count["super_check_count"] for anno in total_sup_annos
    ]
    if len(total_rejection_loop_value_list) > 0:
        avg_rejection_loop_value = sum(total_rejection_loop_value_list) / len(
            total_rejection_loop_value_list
        )
    else:
        avg_rejection_loop_value = 0
    tasks_rejected_max_times = 0
    for anno in total_sup_annos:
        if (
            anno.task.revision_loop_count["super_check_count"]
            >= anno.task.project_id.revision_loop_count
        ):
            tasks_rejected_max_times += 1

    if project_type != None:
        project_type_lower = project_type.lower()
        is_translation_project = True if "translation" in project_type_lower else False

        validated_word_count_list = []
        validated_with_changes_word_count_list = []
        rejected_word_count_list = []
        validated_audio_duration_list = []
        validated_with_changes_audio_duration_list = []
        rejected_audio_duration_list = []
        total_raw_audio_duration_list = []
        total_word_error_rate_rs_list = []
        if is_translation_project or project_type == "SemanticTextualSimilarity_Scale5":
            for anno in validated_objs:
                try:
                    validated_word_count_list.append(anno.task.data["word_count"])
                except:
                    pass
            for anno in validated_with_changes_objs:
                try:
                    validated_with_changes_word_count_list.append(
                        anno.task.data["word_count"]
                    )
                except:
                    pass
            for anno in rejected_objs:
                try:
                    rejected_word_count_list.append(anno.task.data["word_count"])
                except:
                    pass
        elif project_type in get_audio_project_types():
            for anno in validated_objs:
                try:
                    validated_audio_duration_list.append(
                        get_audio_transcription_duration(anno.result)
                    )
                except:
                    pass
            for anno in validated_with_changes_objs:
                try:
                    validated_with_changes_audio_duration_list.append(
                        get_audio_transcription_duration(anno.result)
                    )
                except:
                    pass
            for anno in rejected_objs:
                try:
                    rejected_audio_duration_list.append(
                        get_audio_transcription_duration(anno.result)
                    )
                except:
                    pass
            for anno in total_sup_annos:
                try:
                    total_word_error_rate_rs_list.append(
                        calculate_word_error_rate_between_two_audio_transcription_annotation(
                            anno.result, anno.parent_annotation.result
                        )
                    )
                    total_raw_audio_duration_list.append(
                        anno.task.data["audio_duration"]
                    )
                except:
                    pass
            for anno in total_superchecked_annos:
                try:
                    total_word_error_rate_rs_list.append(
                        calculate_word_error_rate_between_two_audio_transcription_annotation(
                            anno.result, anno.parent_annotation.result
                        )
                    )
                except:
                    pass

        validated_word_count = sum(validated_word_count_list)
        validated_with_changes_word_count = sum(validated_with_changes_word_count_list)
        rejected_word_count = sum(rejected_word_count_list)
        validated_audio_duration = convert_seconds_to_hours(
            sum(validated_audio_duration_list)
        )
        validated_with_changes_audio_duration = convert_seconds_to_hours(
            sum(validated_with_changes_audio_duration_list)
        )
        rejected_audio_duration = convert_seconds_to_hours(
            sum(rejected_audio_duration_list)
        )
        total_raw_audio_duration = convert_seconds_to_hours(
            sum(total_raw_audio_duration_list)
        )
        if len(total_word_error_rate_rs_list) > 0:
            avg_word_error_rate = sum(total_word_error_rate_rs_list) / len(
                total_word_error_rate_rs_list
            )
        else:
            avg_word_error_rate = 0

    result = {
        "SuperChecker Name": userName,
        "Email": email,
        "Participation Type": participation_type,
        "User Role": role,
        "Language": superchecker_languages,
        "Assigned": total_task_count,
        "Validated": validated_objs_count,
        "Validated With Changes": validated_with_changes_objs_count,
        "Rejected": rejected_objs_count,
        "Unvalidated": unvalidated_objs_count,
        "Skipped": skipped_objs_count,
        "Draft": draft_objs_count,
        "Average Rejection Loop Value": round(avg_rejection_loop_value, 2),
        "Tasks Rejected Maximum Time": tasks_rejected_max_times,
    }

    if project_type != None:
        if is_translation_project or project_type == "SemanticTextualSimilarity_Scale5":
            result["Validated Word Count"] = validated_word_count
            result[
                "Validated With Changes Word Count"
            ] = validated_with_changes_word_count
            result["Rejected Word Count"] = rejected_word_count
        elif project_type in get_audio_project_types():
            result["Validated Audio Duration"] = validated_audio_duration
            result[
                "Validated With Changes Audio Duration"
            ] = validated_with_changes_audio_duration
            result["Rejected Audio Duration"] = rejected_audio_duration
            result["Total Raw Audio Duration"] = total_raw_audio_duration
            result["Average Word Error Rate R/S"] = round(avg_word_error_rate, 2)

    return result


def get_review_reports(
    proj_ids,
    userid,
    start_date,
    end_date,
    project_progress_stage=None,
    project_type=None,
):
    user = User.objects.get(id=userid)
    participation_type = user.participation_type
    participation_type = (
        "Full Time"
        if participation_type == 1
        else "Part Time"
        if participation_type == 2
        else "Contract Basis"
        if participation_type == 4
        else "N/A"
    )
    role = get_role_name(user.role)
    userName = user.username
    email = user.email

    reviewer_languages = user.languages

    total_tasks = Task.objects.filter(project_id__in=proj_ids, review_user=userid)

    total_task_count = total_tasks.count()

    accepted_tasks = Annotation.objects.filter(
        annotation_status="accepted",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    accepted_objs_count = accepted_tasks.count()

    superchecked_accepted_annos = Annotation.objects.filter(
        parent_annotation_id__in=accepted_tasks,
        annotation_status__in=[
            "validated",
            "validated_with_changes",
        ],
    )

    superchecked_accepted_annos_count = superchecked_accepted_annos.count()

    accepted_objs_only = accepted_objs_count - superchecked_accepted_annos_count

    acceptedwt_minor_change_tasks = Annotation.objects.filter(
        annotation_status="accepted_with_minor_changes",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    minor_changes = acceptedwt_minor_change_tasks.count()

    superchecked_minor_annos = Annotation.objects.filter(
        parent_annotation_id__in=acceptedwt_minor_change_tasks,
        annotation_status__in=[
            "validated",
            "validated_with_changes",
        ],
    )

    superchecked_minor_annos_count = superchecked_minor_annos.count()

    minor_objs_only = minor_changes - superchecked_minor_annos_count

    acceptedwt_major_change_tasks = Annotation.objects.filter(
        annotation_status="accepted_with_major_changes",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    major_changes = acceptedwt_major_change_tasks.count()

    superchecked_major_annos = Annotation.objects.filter(
        parent_annotation_id__in=acceptedwt_major_change_tasks,
        annotation_status__in=[
            "validated",
            "validated_with_changes",
        ],
    )

    superchecked_major_annos_count = superchecked_major_annos.count()

    major_objs_only = major_changes - superchecked_major_annos_count

    labeled_tasks = Task.objects.filter(
        project_id__in=proj_ids, review_user=userid, task_status="annotated"
    )
    labeled_tasks_count = labeled_tasks.count()

    to_be_revised_tasks = Annotation.objects.filter(
        annotation_status="to_be_revised",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    to_be_revised_tasks_count = to_be_revised_tasks.count()

    skipped_tasks = Annotation.objects.filter(
        annotation_status="skipped",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    skipped_tasks_count = skipped_tasks.count()

    draft_tasks = Annotation.objects.filter(
        annotation_status="draft",
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    draft_tasks_count = draft_tasks.count()

    total_rev_annos = Annotation.objects.filter(
        task__project_id__in=proj_ids,
        task__review_user=userid,
        annotation_type=REVIEWER_ANNOTATION,
        updated_at__range=[start_date, end_date],
    )

    total_rev_sup_annos = Annotation.objects.filter(
        parent_annotation__in=total_rev_annos
    )

    total_superchecked_annos = total_rev_sup_annos.filter(
        task__task_status="super_checked"
    )

    total_rejection_loop_value_list = [
        anno.task.revision_loop_count["super_check_count"]
        for anno in total_rev_sup_annos
    ]
    if len(total_rejection_loop_value_list) > 0:
        avg_rejection_loop_value = sum(total_rejection_loop_value_list) / len(
            total_rejection_loop_value_list
        )
    else:
        avg_rejection_loop_value = 0
    tasks_rejected_max_times = 0
    for anno in total_rev_sup_annos:
        if (
            anno.task.revision_loop_count["super_check_count"]
            >= anno.task.project_id.revision_loop_count
        ):
            tasks_rejected_max_times += 1

    if project_type != None:
        project_type_lower = project_type.lower()
        is_translation_project = True if "translation" in project_type_lower else False
        total_rev_annos_accepted = total_rev_annos.filter(
            annotation_status__in=[
                "accepted",
                "accepted_with_minor_changes",
                "accepted_with_major_changes",
            ]
        )
        total_audio_duration_list = []
        total_raw_audio_duration_list = []
        total_word_count_list = []
        total_word_error_rate_ar_list = []
        total_word_error_rate_rs_list = []
        if is_translation_project or project_type == "SemanticTextualSimilarity_Scale5":
            for anno in total_rev_annos_accepted:
                total_word_count_list.append(anno.task.data["word_count"])
        elif project_type in get_audio_project_types():
            for anno in total_rev_annos_accepted:
                try:
                    total_audio_duration_list.append(
                        get_audio_transcription_duration(anno.result)
                    )
                    total_raw_audio_duration_list.append(
                        anno.task.data["audio_duration"]
                    )
                    total_word_error_rate_ar_list.append(
                        calculate_word_error_rate_between_two_audio_transcription_annotation(
                            anno.result, anno.parent_annotation.result
                        )
                    )
                except:
                    pass
            for anno in total_superchecked_annos:
                try:
                    total_word_error_rate_rs_list.append(
                        calculate_word_error_rate_between_two_audio_transcription_annotation(
                            anno.result, anno.parent_annotation.result
                        )
                    )
                except:
                    pass

        total_word_count = sum(total_word_count_list)
        total_audio_duration = convert_seconds_to_hours(sum(total_audio_duration_list))
        total_raw_audio_duration = convert_seconds_to_hours(
            sum(total_raw_audio_duration_list)
        )
        if len(total_word_error_rate_ar_list) > 0:
            avg_word_error_rate_ar = sum(total_word_error_rate_ar_list) / len(
                total_word_error_rate_ar_list
            )
        else:
            avg_word_error_rate_ar = 0
        if len(total_word_error_rate_rs_list) > 0:
            avg_word_error_rate_rs = sum(total_word_error_rate_rs_list) / len(
                total_word_error_rate_rs_list
            )
        else:
            avg_word_error_rate_rs = 0

    if project_progress_stage == SUPERCHECK_STAGE:
        annotations_of_superchecker_validated = Annotation.objects.filter(
            task__project_id__in=proj_ids,
            annotation_status="validated",
            annotation_type=SUPER_CHECKER_ANNOTATION,
            parent_annotation__updated_at__range=[start_date, end_date],
        )
        parent_anno_ids = [
            ann.parent_annotation_id for ann in annotations_of_superchecker_validated
        ]
        accepted_validated_tasks = Annotation.objects.filter(
            id__in=parent_anno_ids,
            completed_by=userid,
        )

        annotations_of_superchecker_validated_with_changes = Annotation.objects.filter(
            task__project_id__in=proj_ids,
            annotation_status="validated_with_changes",
            annotation_type=SUPER_CHECKER_ANNOTATION,
            parent_annotation__updated_at__range=[start_date, end_date],
        )
        parent_anno_ids = [
            ann.parent_annotation_id
            for ann in annotations_of_superchecker_validated_with_changes
        ]
        accepted_validated_with_changes_tasks = Annotation.objects.filter(
            id__in=parent_anno_ids,
            completed_by=userid,
        )

        annotations_of_superchecker_rejected = Annotation.objects.filter(
            task__project_id__in=proj_ids,
            annotation_status="rejected",
            annotation_type=SUPER_CHECKER_ANNOTATION,
            parent_annotation__updated_at__range=[start_date, end_date],
        )
        parent_anno_ids = [
            ann.parent_annotation_id for ann in annotations_of_superchecker_rejected
        ]
        accepted_rejected_tasks = Annotation.objects.filter(
            id__in=parent_anno_ids, completed_by=userid, annotation_status="rejected"
        )

        result = {
            "Reviewer Name": userName,
            "Email": email,
            "Participation Type": participation_type,
            "User Role": role,
            "Language": reviewer_languages,
            "Assigned": total_task_count,
            "Accepted": accepted_objs_only,
            "Accepted With Minor Changes": minor_objs_only,
            "Accepted With Major Changes": major_objs_only,
            "Unreviewed": labeled_tasks_count,
            "To Be Revised": to_be_revised_tasks_count,
            "Skipped": skipped_tasks_count,
            "Draft": draft_tasks_count,
            "Validated": accepted_validated_tasks.count(),
            "Validated With Changes": accepted_validated_with_changes_tasks.count(),
            "Rejected": accepted_rejected_tasks.count(),
            "Average Rejection Loop Value": round(avg_rejection_loop_value, 2),
            "Tasks Rejected Maximum Time": tasks_rejected_max_times,
        }

        if project_type != None:
            if (
                is_translation_project
                or project_type == "SemanticTextualSimilarity_Scale5"
            ):
                result["Total Word Count"] = total_word_count
            elif project_type in get_audio_project_types():
                result["Total Segments Duration"] = total_audio_duration
                result["Total Raw Audio Duration"] = total_raw_audio_duration
                result["Average Word Error Rate A/R"] = round(avg_word_error_rate_ar, 2)
                result["Average Word Error Rate R/S"] = round(avg_word_error_rate_rs, 2)

        return result

    result = {
        "Reviewer Name": userName,
        "Email": email,
        "Participation Type": participation_type,
        "User Role": role,
        "Language": reviewer_languages,
        "Assigned": total_task_count,
        "Accepted": accepted_objs_count,
        "Accepted With Minor Changes": minor_changes,
        "Accepted With Major Changes": major_changes,
        "Unreviewed": labeled_tasks_count,
        "To Be Revised": to_be_revised_tasks_count,
        "Skipped": skipped_tasks_count,
        "Draft": draft_tasks_count,
        "Average Rejection Loop Value": round(avg_rejection_loop_value, 2),
        "Tasks Rejected Maximum Time": tasks_rejected_max_times,
    }

    if project_type != None:
        if is_translation_project or project_type == "SemanticTextualSimilarity_Scale5":
            result["Total Word Count"] = total_word_count
        elif project_type in get_audio_project_types():
            result["Total Segments Duration"] = total_audio_duration
            result["Total Raw Audio Duration"] = total_raw_audio_duration
            result["Average Word Error Rate A/R"] = round(avg_word_error_rate_ar, 2)
            result["Average Word Error Rate R/S"] = round(avg_word_error_rate_rs, 2)

    return result


class WorkspaceViewSet(viewsets.ModelViewSet):
    queryset = Workspace.objects.all()
    serializer_class = WorkspaceSerializer
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        if int(request.user.role) == User.WORKSPACE_MANAGER:
            data = self.queryset.filter(
                managers=request.user,
                is_archived=False,
                organization=request.user.organization,
            )
            serializer = WorkspaceSerializer(data, many=True)
            return Response(serializer.data)
        elif (int(request.user.role) == User.ORGANIZATION_OWNER) or (
            request.user.is_superuser
        ):
            data = self.queryset.filter(organization=request.user.organization)
            serializer = WorkspaceSerializer(data, many=True)
            return Response(serializer.data)
        else:
            return Response(
                {"message": "Not authorized!"}, status=status.HTTP_403_FORBIDDEN
            )

    @is_particular_workspace_manager
    def retrieve(self, request, pk=None, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @is_workspace_creator
    def create(self, request, *args, **kwargs):
        # TODO: Make sure to add the user to the workspace and created_by
        # return super().create(request, *args, **kwargs)
        try:
            data = self.serializer_class(data=request.data)
            if data.is_valid():
                if request.user.organization == data.validated_data["organization"]:
                    obj = data.save()
                    obj.members.add(request.user)
                    obj.created_by = request.user
                    obj.save()
                    return Response(
                        {"message": "Workspace created!"},
                        status=status.HTTP_201_CREATED,
                    )
                else:
                    return Response(
                        {
                            "message": "You are not authorized to create workspace for this organization!"
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )
            else:
                return Response(
                    {"message": "Invalid Data"}, status=status.HTTP_400_BAD_REQUEST
                )
        except:
            return Response(
                {"message": "Invalid Data"}, status=status.HTTP_400_BAD_REQUEST
            )

    @is_particular_workspace_manager
    @workspace_is_archived
    def update(self, request, pk=None, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @is_particular_workspace_manager
    @workspace_is_archived
    def partial_update(self, request, pk=None, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, pk=None, *args, **kwargs):
        return Response(
            {"message": "Deleting of Workspaces is not supported!"},
            status=status.HTTP_403_FORBIDDEN,
        )


class WorkspaceCustomViewSet(viewsets.ViewSet):
    @swagger_auto_schema(responses={200: UserProfileSerializer})
    @is_particular_workspace_manager
    @action(
        detail=True, methods=["GET"], name="Get Workspace members", url_name="members"
    )
    def members(self, request, pk=None):
        """
        Get all members of a workspace
        """
        try:
            workspace = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        members = workspace.members.all()
        serializer = UserProfileSerializer(members, many=True)
        return Response(serializer.data)

    # TODO : add exceptions
    @action(
        detail=True,
        methods=["POST"],
        name="Archive Workspace",
        url_name="archive",
    )
    @is_particular_organization_owner
    def archive(self, request, pk=None, *args, **kwargs):
        workspace = Workspace.objects.get(pk=pk)
        workspace.is_archived = not workspace.is_archived
        workspace.save()
        return Response({"done": True}, status=status.HTTP_200_OK)

    # TODO: Add serializer
    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "ids": openapi.Schema(type=openapi.TYPE_STRING, format="email")
            },
            required=["ids"],
        ),
        responses={
            200: "Done",
            404: "User with such Username does not exist!",
            400: "Bad request,Some exception occured",
        },
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
    )
    @action(
        detail=True, methods=["POST"], name="Assign Manager", url_name="assign_manager"
    )
    @is_particular_organization_owner
    def assign_manager(self, request, pk=None, *args, **kwargs):
        """
        API for assigning manager to a workspace
        """
        ret_dict = {}
        ret_status = 0
        if "ids" in dict(request.data):
            ids = request.data.get("ids", "")
        else:
            return Response(
                {"message": "key doesnot match"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for id1 in ids:
            try:
                user = User.objects.get(id=id1)
            except User.DoesNotExist:
                return Response(
                    {"message": "User with such id does not exist!"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if user.role == User.ANNOTATOR or user.role == User.REVIEWER:
                return Response(
                    {"message": "One or more users do not have access to be manager"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                workspace = Workspace.objects.get(pk=pk)
            except Workspace.DoesNotExist:
                ret_dict["message"] = "Workspace not found!"
                ret_status = status.HTTP_404_NOT_FOUND
                return Response(ret_dict, status=ret_status)
            if user in workspace.managers.all():
                ret_dict["message"] = "User already exists in workspace!"
                ret_status = status.HTTP_400_BAD_REQUEST
                return Response(ret_dict, status=ret_status)
            workspace.managers.add(user)
            workspace.members.add(user)
            workspace.save()
            serializer = WorkspaceManagerSerializer(workspace, many=False)
        return Response({"done": True}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        name="Unassign Manager",
        url_name="unassign_manager",
    )
    @is_particular_organization_owner
    def unassign_manager(self, request, pk=None, *args, **kwargs):
        """
        API Endpoint for unassigning an workspace manager
        """
        ret_dict = {}
        ret_status = 0
        if "ids" in dict(request.data):
            ids = request.data.get("ids", "")
        else:
            return Response(
                {"message": "key doesnot match"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace = Workspace.objects.get(pk=pk)

            for id1 in ids:
                try:
                    user = User.objects.get(id=id1)
                except User.DoesNotExist:
                    return Response(
                        {"message": "User with such id does not exist!"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if user not in workspace.managers.all():
                    return Response(
                        {"message": "user not found in workspace"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                else:
                    workspace.managers.remove(user)
            return Response({"done": True}, status=status.HTTP_200_OK)
        except Workspace.DoesNotExist:
            ret_dict["message"] = "Workspace not found!"
            ret_status = status.HTTP_404_NOT_FOUND
            return Response(ret_dict, status=ret_status)

    @swagger_auto_schema(
        method="get",
        responses={200: ProjectSerializer(many=True)},
        manual_parameters=[
            openapi.Parameter(
                "only_active",
                openapi.IN_QUERY,
                description=(
                    "It is passed as true to get all the projects which are not archived,to get all it is passed as false"
                ),
                type=openapi.TYPE_BOOLEAN,
                required=False,
            ),
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            ),
        ],
    )
    @action(
        detail=True,
        methods=["GET"],
        name="Get Projects",
        url_path="projects",
        url_name="projects",
    )
    @is_particular_workspace_manager
    def get_projects(self, request, pk=None):
        """
        API for getting all projects of a workspace
        """
        only_active = str(request.GET.get("only_active", "false"))
        only_active = True if only_active == "true" else False
        try:
            workspace = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if request.user.role == User.ANNOTATOR:
            projects = Project.objects.filter(
                annotators=request.user, workspace_id=workspace
            )
        else:
            projects = Project.objects.filter(workspace_id=workspace)
        if only_active == True:
            projects = projects.filter(is_archived=False)
        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["POST"],
        name="Workspace Project Details",
        url_path="project_analytics",
        url_name="project_analytics",
    )
    @is_particular_workspace_manager
    def project_analytics(self, request, pk=None):
        """
        API for getting project_analytics of a workspace
        """
        try:
            ws = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        user_id = request.user.id
        tgt_language = request.data.get("tgt_language")
        project_type = request.data.get("project_type")
        # enable_task_reviews = request.data.get("enable_task_reviews")

        send_project_analysis_reports_mail_ws.delay(
            pk=pk,
            user_id=user_id,
            tgt_language=tgt_language,
            project_type=project_type,
        )

        ret_status = status.HTTP_200_OK
        return Response({"message": "Email scheduled successfully"}, status=ret_status)

    @action(
        detail=True,
        methods=["POST"],
        name="Workspace member Details",
        url_path="user_analytics",
        url_name="user_analytics",
    )
    def user_analytics(self, request, pk=None):
        """
        API for getting user_analytics of a workspace
        """
        try:
            ws = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        user_id = request.user.id
        from_date = request.data.get("from_date")
        to_date = request.data.get("to_date")
        from_date = from_date + " 00:00"
        to_date = to_date + " 23:59"
        project_progress_stage = request.data.get("project_progress_stage")
        reports_type = request.data.get("reports_type")
        tgt_language = request.data.get("tgt_language")
        project_type = request.data.get("project_type")
        project_type_lower = project_type.lower()
        is_translation_project = True if "translation" in project_type_lower else False
        # enable_task_reviews = request.data.get("enable_task_reviews")

        cond, invalid_message = is_valid_date(from_date)
        if not cond:
            return Response(
                {"message": invalid_message}, status=status.HTTP_400_BAD_REQUEST
            )
        cond, invalid_message = is_valid_date(to_date)
        if not cond:
            return Response(
                {"message": invalid_message}, status=status.HTTP_400_BAD_REQUEST
            )
        start_date = datetime.strptime(from_date, "%Y-%m-%d %H:%M")
        end_date = datetime.strptime(to_date, "%Y-%m-%d %H:%M")
        final_reports = []

        if start_date > end_date:
            return Response(
                {"message": "'To' Date should be after 'From' Date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if reports_type == "review":
            proj_objs = Project.objects.filter(workspace_id=pk)
            if project_type != None:
                proj_objs = proj_objs.filter(project_type=project_type)
            if project_progress_stage == None:
                review_projects = [
                    pro for pro in proj_objs if pro.project_stage > ANNOTATION_STAGE
                ]
            elif project_progress_stage in [REVIEW_STAGE, SUPERCHECK_STAGE]:
                review_projects = [
                    pro
                    for pro in proj_objs
                    if pro.project_stage == project_progress_stage
                ]
            else:
                final_response = {
                    "message": "Annotation stage projects don't have review reports."
                }
                return Response(final_response, status=status.HTTP_400_BAD_REQUEST)

            workspace_reviewer_list = []
            review_projects_ids = []
            for review_project in review_projects:
                reviewer_names_list = review_project.annotation_reviewers.all()
                reviewer_ids = [name.id for name in reviewer_names_list]
                workspace_reviewer_list.extend(reviewer_ids)
                review_projects_ids.append(review_project.id)

            workspace_reviewer_list = list(set(workspace_reviewer_list))

            if (
                request.user.role == User.ORGANIZATION_OWNER
                or request.user.role == User.WORKSPACE_MANAGER
                or request.user.is_superuser
            ):
                for id in workspace_reviewer_list:
                    reviewer_projs = Project.objects.filter(
                        workspace_id=pk,
                        annotation_reviewers=id,
                        id__in=review_projects_ids,
                    )
                    reviewer_projs_ids = [
                        review_proj.id for review_proj in reviewer_projs
                    ]

                    result = get_review_reports(
                        reviewer_projs_ids,
                        id,
                        start_date,
                        end_date,
                        project_progress_stage,
                        project_type,
                    )
                    final_reports.append(result)
            elif user_id in workspace_reviewer_list:
                reviewer_projs = Project.objects.filter(
                    workspace_id=pk,
                    annotation_reviewers=user_id,
                    id__in=review_projects_ids,
                )
                reviewer_projs_ids = [review_proj.id for review_proj in reviewer_projs]

                result = get_review_reports(
                    reviewer_projs_ids,
                    user_id,
                    start_date,
                    end_date,
                    project_progress_stage,
                    project_type,
                )
                final_reports.append(result)

            else:
                final_reports = {
                    "message": "You do not have enough permissions to access this view!"
                }
                return Response(final_reports)

        elif reports_type == "supercheck":
            proj_objs = Project.objects.filter(workspace_id=pk)
            if project_type != None:
                proj_objs = proj_objs.filter(project_type=project_type)
            supercheck_projects = [
                pro for pro in proj_objs if pro.project_stage > REVIEW_STAGE
            ]

            workspace_superchecker_list = []
            supercheck_projects_ids = []
            for supercheck_project in supercheck_projects:
                superchecker_names_list = supercheck_project.review_supercheckers.all()
                superchecker_ids = [name.id for name in superchecker_names_list]
                workspace_superchecker_list.extend(superchecker_ids)
                supercheck_projects_ids.append(supercheck_project.id)

            workspace_superchecker_list = list(set(workspace_superchecker_list))
            final_reports = []

            if (
                request.user.role == User.ORGANIZATION_OWNER
                or request.user.role == User.WORKSPACE_MANAGER
                or request.user.is_superuser
            ):
                for id in workspace_superchecker_list:
                    superchecker_projs = Project.objects.filter(
                        workspace_id=pk,
                        review_supercheckers=id,
                        id__in=supercheck_projects_ids,
                    )
                    superchecker_projs_ids = [
                        supercheck_proj.id for supercheck_proj in superchecker_projs
                    ]

                    result = get_supercheck_reports(
                        superchecker_projs_ids, id, start_date, end_date, project_type
                    )
                    final_reports.append(result)
            elif user_id in workspace_superchecker_list:
                superchecker_projs = Project.objects.filter(
                    workspace_id=pk,
                    review_supercheckers=id,
                    id__in=supercheck_projects_ids,
                )
                superchecker_projs_ids = [
                    supercheck_proj.id for supercheck_proj in superchecker_projs
                ]

                result = get_supercheck_reports(
                    superchecker_projs_ids, user_id, start_date, end_date, project_type
                )
                final_reports.append(result)

            else:
                final_reports = {
                    "message": "You do not have enough permissions to access this view!"
                }

                return Response(final_reports)

        if not (
            request.user.is_authenticated
            and (
                request.user.role == User.ORGANIZATION_OWNER
                or request.user.role == User.WORKSPACE_MANAGER
                or request.user.is_superuser
            )
        ):
            final_response = {
                "message": "You do not have enough permissions to access this view!"
            }
            return Response(final_response, status=status.HTTP_400_BAD_REQUEST)

        send_user_analysis_reports_mail_ws.delay(
            pk=pk,
            user_id=user_id,
            tgt_language=tgt_language,
            project_type=project_type,
            project_progress_stage=project_progress_stage,
            start_date=start_date,
            end_date=end_date,
            is_translation_project=is_translation_project,
            final_reports=final_reports,
        )

        return Response(
            {"message": "Email scheduled successfully"}, status=status.HTTP_200_OK
        )

    @action(
        detail=True,
        methods=["GET"],
        name="Get Cumulative tasks completed ",
        url_name="cumulative_tasks_count_all",
    )
    def cumulative_tasks_count_all(self, request, pk=None):
        try:
            ws = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        metainfo = False
        if "metainfo" in dict(request.query_params):
            metainfo = request.query_params["metainfo"]
            if metainfo == "true" or metainfo == "True":
                metainfo = True
        project_types = [
            "ContextualTranslationEditing",
            "ContextualSentenceVerification",
            "SemanticTextualSimilarity_Scale5",
            "AudioTranscriptionEditing",
            "AudioTranscription",
            "AudioSegmentation",
        ]
        if "project_type" in dict(request.query_params):
            project_type = request.query_params["project_type"]
            project_types = [project_type]
        final_result_for_all_types = {}
        for project_type in project_types:
            proj_objs = []
            proj_objs = Project.objects.filter(
                workspace_id=pk, project_type=project_type
            )

            languages = list(set([proj.tgt_language for proj in proj_objs]))
            general_lang = []
            other_lang = []
            for lang in languages:
                proj_lang_filter = proj_objs.filter(tgt_language=lang)
                annotation_tasks_count = 0
                reviewer_task_count = 0
                reviewer_tasks = Task.objects.filter(
                    project_id__in=proj_lang_filter,
                    project_id__project_stage__in=[REVIEW_STAGE, SUPERCHECK_STAGE],
                    task_status__in=["reviewed", "exported", "super_checked"],
                )

                annotation_tasks = Task.objects.filter(
                    project_id__in=proj_lang_filter,
                    task_status__in=[
                        "annotated",
                        "reviewed",
                        "exported",
                        "super_checked",
                    ],
                )

                if metainfo == True:
                    result = {}

                    if project_type in get_audio_project_types():
                        # review audio duration calclation
                        total_rev_duration_list = []

                        for each_task in reviewer_tasks:
                            try:
                                if each_task.task_status == "reviewed":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=REVIEWER_ANNOTATION,
                                    )[0]
                                elif each_task.task_status == "super_checked":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=SUPER_CHECKER_ANNOTATION,
                                    )[0]
                                else:
                                    anno = each_task.correct_annotation
                                total_rev_duration_list.append(
                                    get_audio_transcription_duration(anno.result)
                                )
                            except:
                                pass
                        rev_total_duration = sum(total_rev_duration_list)
                        rev_total_time = convert_seconds_to_hours(rev_total_duration)

                        # annotation audio duration calclation

                        total_ann_duration_list = []

                        for each_task in annotation_tasks:
                            try:
                                if each_task.task_status == "reviewed":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=REVIEWER_ANNOTATION,
                                    )[0]
                                elif each_task.task_status == "exported":
                                    anno = each_task.correct_annotation
                                elif each_task.task_status == "super_checked":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=SUPER_CHECKER_ANNOTATION,
                                    )[0]
                                else:
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=ANNOTATOR_ANNOTATION,
                                    )[0]
                                total_ann_duration_list.append(
                                    get_audio_transcription_duration(anno.result)
                                )
                            except:
                                pass
                        ann_total_duration = sum(total_ann_duration_list)
                        ann_total_time = convert_seconds_to_hours(ann_total_duration)

                        result = {
                            "language": lang,
                            "ann_cumulative_aud_duration": ann_total_time,
                            "rew_cumulative_aud_duration": rev_total_time,
                        }

                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        total_rev_word_count_list = []
                        for reviewer_tas in reviewer_tasks:
                            try:
                                total_rev_word_count_list.append(
                                    reviewer_tas.data["word_count"]
                                )
                            except:
                                pass

                        total_ann_word_count_list = []

                        for annotation_tas in annotation_tasks:
                            try:
                                total_ann_word_count_list.append(
                                    annotation_tas.data["word_count"]
                                )
                            except:
                                pass

                        result = {
                            "language": lang,
                            "ann_cumulative_word_count": sum(total_ann_word_count_list),
                            "rew_cumulative_word_count": sum(total_rev_word_count_list),
                        }

                else:
                    reviewer_task_count = reviewer_tasks.count()

                    annotation_tasks_count = annotation_tasks.count()

                    result = {
                        "language": lang,
                        "ann_cumulative_tasks_count": annotation_tasks_count,
                        "rew_cumulative_tasks_count": reviewer_task_count,
                    }

                if lang == None or lang == "":
                    other_lang.append(result)
                else:
                    general_lang.append(result)

            ann_task_count = 0
            rew_task_count = 0
            ann_word_count = 0
            rew_word_count = 0
            ann_aud_dur = 0
            rew_aud_dur = 0
            for dat in other_lang:
                if metainfo != True:
                    ann_task_count += dat["ann_cumulative_tasks_count"]
                    rew_task_count += dat["rew_cumulative_tasks_count"]
                else:
                    if project_type in get_audio_project_types():
                        ann_aud_dur += convert_hours_to_seconds(
                            dat["ann_cumulative_aud_duration"]
                        )
                        rew_aud_dur += convert_hours_to_seconds(
                            dat["rew_cumulative_aud_duration"]
                        )
                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        ann_word_count += dat["ann_cumulative_word_count"]
                        rew_word_count += dat["rew_cumulative_word_count"]

            if len(other_lang) > 0:
                if metainfo != True:
                    other_language = {
                        "language": "Others",
                        "ann_cumulative_tasks_count": ann_task_count,
                        "rew_cumulative_tasks_count": rew_task_count,
                    }
                else:
                    if project_type in get_audio_project_types():
                        other_language = {
                            "language": "Others",
                            "ann_cumulative_aud_duration": convert_seconds_to_hours(
                                ann_aud_dur
                            ),
                            "rew_cumulative_aud_duration": convert_seconds_to_hours(
                                rew_aud_dur
                            ),
                        }

                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        other_language = {
                            "language": "Others",
                            "ann_cumulative_word_count": ann_word_count,
                            "rew_cumulative_word_count": rew_word_count,
                        }

                general_lang.append(other_language)
            try:
                final_result = sorted(
                    general_lang, key=lambda x: x["language"], reverse=False
                )
            except:
                final_result = []

            if metainfo == True and not (
                (project_type in get_audio_project_types())
                or (
                    project_type in get_translation_dataset_project_types()
                    or "ConversationTranslation" in project_type
                )
            ):
                pass
            else:
                final_result_for_all_types[project_type] = final_result
        return Response(final_result_for_all_types)

    @action(
        detail=True,
        methods=["POST"],
        name="Get Cumulative tasks completed ",
        url_name="cumulative_tasks_count",
    )
    def cumulative_tasks_count(self, request, pk=None):
        try:
            ws = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        metainfo = False
        if "metainfo" in dict(request.query_params):
            metainfo = request.query_params["metainfo"]
            if metainfo == "true" or metainfo == "True":
                metainfo = True
        project_type = request.data.get("project_type")
        reviewer_reports = request.data.get("reviewer_reports")
        supercheck_reports = request.data.get("supercheck_reports")
        proj_objs = []
        if reviewer_reports == True:
            proj_objs = Project.objects.filter(
                workspace_id=pk,
                project_type=project_type,
                project_stage__in=[REVIEW_STAGE, SUPERCHECK_STAGE],
            )
        elif supercheck_reports == True:
            proj_objs = Project.objects.filter(
                workspace_id=pk,
                project_type=project_type,
                project_stage__in=[SUPERCHECK_STAGE],
            )
        else:
            proj_objs = Project.objects.filter(
                workspace_id=pk, project_type=project_type
            )

        proj_objs_languages = Project.objects.filter(
            workspace_id=pk, project_type=project_type
        )

        languages = list(set([proj.tgt_language for proj in proj_objs_languages]))
        general_lang = []
        other_lang = []
        for lang in languages:
            proj_lang_filter = proj_objs.filter(tgt_language=lang)
            tasks_count = 0
            if reviewer_reports == True:
                tasks = Task.objects.filter(
                    project_id__in=proj_lang_filter,
                    project_id__tgt_language=lang,
                    task_status__in=[
                        "reviewed",
                        "exported",
                        "super_checked",
                    ],
                )
                tasks_count = tasks.count()

            elif supercheck_reports == True:
                tasks = Task.objects.filter(
                    project_id__in=proj_lang_filter,
                    project_id__tgt_language=lang,
                    task_status__in=[
                        "super_checked",
                    ],
                )
                tasks_count = tasks.count()

            else:
                tasks = Task.objects.filter(
                    project_id__in=proj_lang_filter,
                    project_id__tgt_language=lang,
                    task_status__in=[
                        "annotated",
                        "reviewed",
                        "exported",
                        "super_checked",
                    ],
                )
                tasks_count = tasks.count()

            if metainfo == True:
                result = {}

                if project_type in get_audio_project_types():
                    total_rev_duration_list = []
                    total_ann_duration_list = []
                    total_sup_duration_list = []

                    for each_task in tasks:
                        if reviewer_reports == True:
                            try:
                                if each_task.task_status == "reviewed":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=REVIEWER_ANNOTATION,
                                    )[0]
                                elif each_task.task_status == "super_checked":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=SUPER_CHECKER_ANNOTATION,
                                    )[0]
                                else:
                                    anno = each_task.correct_annotation
                                total_rev_duration_list.append(
                                    get_audio_transcription_duration(anno.result)
                                )
                            except:
                                pass
                        elif supercheck_reports == True:
                            try:
                                if each_task.task_status == "super_checked":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=SUPER_CHECKER_ANNOTATION,
                                    )[0]
                                else:
                                    anno = each_task.correct_annotation
                                total_sup_duration_list.append(
                                    get_audio_transcription_duration(anno.result)
                                )
                            except:
                                pass
                        else:
                            try:
                                if each_task.task_status == "reviewed":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=REVIEWER_ANNOTATION,
                                    )[0]
                                elif each_task.task_status == "exported":
                                    anno = each_task.correct_annotation
                                elif each_task.task_status == "super_checked":
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=SUPER_CHECKER_ANNOTATION,
                                    )[0]
                                else:
                                    anno = Annotation.objects.filter(
                                        task=each_task,
                                        annotation_type=ANNOTATOR_ANNOTATION,
                                    )[0]
                                total_ann_duration_list.append(
                                    get_audio_transcription_duration(anno.result)
                                )
                            except:
                                pass
                    if reviewer_reports == True:
                        rev_total_duration = sum(total_rev_duration_list)
                        rev_total_time = convert_seconds_to_hours(rev_total_duration)
                        result = {
                            "language": lang,
                            "cumulative_aud_duration": rev_total_time,
                        }
                    elif supercheck_reports == True:
                        sup_total_duration = sum(total_sup_duration_list)
                        sup_total_time = convert_seconds_to_hours(sup_total_duration)
                        result = {
                            "language": lang,
                            "cumulative_aud_duration": sup_total_time,
                        }
                    else:
                        ann_total_duration = sum(total_ann_duration_list)
                        ann_total_time = convert_seconds_to_hours(ann_total_duration)
                        result = {
                            "language": lang,
                            "cumulative_aud_duration": ann_total_time,
                        }
                elif (
                    project_type in get_translation_dataset_project_types()
                    or "ConversationTranslation" in project_type
                ):
                    total_rev_word_count_list = []
                    total_ann_word_count_list = []
                    total_sup_word_count_list = []

                    for each_task in tasks:
                        if reviewer_reports == True:
                            try:
                                total_rev_word_count_list.append(
                                    each_task.data["word_count"]
                                )
                            except:
                                pass
                        elif supercheck_reports == True:
                            try:
                                total_sup_word_count_list.append(
                                    each_task.data["word_count"]
                                )
                            except:
                                pass
                        else:
                            try:
                                total_ann_word_count_list.append(
                                    each_task.data["word_count"]
                                )
                            except:
                                pass
                    if reviewer_reports == True:
                        result = {
                            "language": lang,
                            "cumulative_word_count": sum(total_rev_word_count_list),
                        }
                    elif supercheck_reports == True:
                        result = {
                            "language": lang,
                            "cumulative_word_count": sum(total_sup_word_count_list),
                        }
                    else:
                        result = {
                            "language": lang,
                            "cumulative_word_count": sum(total_ann_word_count_list),
                        }
            else:
                result = {"language": lang, "cumulative_tasks_count": tasks_count}

            if lang == None or lang == "":
                other_lang.append(result)
            else:
                general_lang.append(result)

        other_count = 0
        other_word_count = 0
        other_aud_dur = 0
        for dat in other_lang:
            if metainfo != True:
                other_count += dat["cumulative_tasks_count"]
            else:
                if project_type in get_audio_project_types():
                    other_aud_dur += convert_hours_to_seconds(
                        dat["cumulative_aud_duration"]
                    )
                elif (
                    project_type in get_translation_dataset_project_types()
                    or "ConversationTranslation" in project_type
                ):
                    other_word_count += dat["cumulative_word_count"]
        if len(other_lang) > 0:
            if metainfo != True:
                other_language = {
                    "language": "Others",
                    "cumulative_tasks_count": other_count,
                }
            else:
                if project_type in get_audio_project_types():
                    other_language = {
                        "language": "Others",
                        "cumulative_aud_duration": convert_seconds_to_hours(
                            other_aud_dur
                        ),
                    }
                elif (
                    project_type in get_translation_dataset_project_types()
                    or "ConversationTranslation" in project_type
                ):
                    other_language = {
                        "language": "Others",
                        "cumulative_word_count": other_word_count,
                    }

            general_lang.append(other_language)

        try:
            final_result = sorted(
                general_lang, key=lambda x: x["language"], reverse=False
            )
        except:
            final_result = []
        if metainfo == True and not (
            (project_type in get_audio_project_types())
            or (
                project_type in get_translation_dataset_project_types()
                or "ConversationTranslation" in project_type
            )
        ):
            final_result = []
        return Response(final_result)

    @action(
        detail=True,
        methods=["POST"],
        name="Get tasks completed based on periods ",
        url_name="periodical_tasks_count",
    )
    def periodical_tasks_count(self, request, pk=None):
        try:
            ws = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        metainfo = False
        if "metainfo" in dict(request.query_params):
            metainfo = request.query_params["metainfo"]
            if metainfo == "true" or metainfo == "True":
                metainfo = True
        project_type = request.data.get("project_type")
        periodical_type = request.data.get("periodical_type")

        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        reviewer_reports = request.data.get("reviewer_reports")
        supercheck_reports = request.data.get("supercheck_reports")

        ws_created_date = ws.created_at
        present_date = datetime.now(timezone.utc)

        if start_date != None:
            date1 = start_date
            ws_created_date = datetime(
                int(date1.split("-")[0]),
                int(date1.split("-")[1]),
                int(date1.split("-")[2]),
                tzinfo=timezone(offset=timedelta()),
            )
        if end_date != None:
            date2 = end_date
            present_date = datetime(
                int(date2.split("-")[0]),
                int(date2.split("-")[1]),
                int(date2.split("-")[2]),
                tzinfo=timezone(offset=timedelta()),
            )

        periodical_list = []
        if periodical_type == "weekly":
            periodical_list.append(ws_created_date)
            while ws_created_date <= present_date:
                ws_created_date = ws_created_date + timedelta(days=7)
                if ws_created_date <= present_date:
                    periodical_list.append(ws_created_date)
                else:
                    periodical_list.append(present_date + timedelta(days=1))

        elif periodical_type == "monthly":
            start_date = ws_created_date
            end_date = present_date

            periodical_list.append(start_date)
            count = 1
            start = start_date
            while start <= end_date:
                start = start_date + relativedelta.relativedelta(months=count)
                if (
                    start_date.day == 29
                    and start.month == 2
                    and (not calendar.isleap(start.year))
                ):
                    start = start + timedelta(days=1)
                if start_date.day == 30 and start.month == 2:
                    start = start + timedelta(days=1)
                if start_date.day == 31 and start.month in [2, 4, 6, 9, 11]:
                    start = start + timedelta(days=1)
                count += 1
                if start <= end_date:
                    periodical_list.append(start)
                else:
                    periodical_list.append(end_date + timedelta(days=1))

        elif periodical_type == "yearly":
            start_date = ws_created_date
            end_date = present_date

            periodical_list.append(start_date)
            count = 1
            start = start_date
            while start <= end_date:
                start = start_date + relativedelta.relativedelta(years=count)
                if (
                    start_date.day == 29
                    and start.month == 2
                    and (not calendar.isleap(start.year))
                ):
                    start = start + timedelta(days=1)

                count += 1
                if start <= end_date:
                    periodical_list.append(start)
                else:
                    periodical_list.append(end_date + timedelta(days=1))
        proj_objs = []
        if reviewer_reports == True:
            proj_objs = Project.objects.filter(
                workspace_id=pk,
                project_type=project_type,
                project_stage__in=[REVIEW_STAGE, SUPERCHECK_STAGE],
            )
        elif supercheck_reports == True:
            proj_objs = Project.objects.filter(
                workspace_id=pk,
                project_type=project_type,
                project_stage__in=[SUPERCHECK_STAGE],
            )
        else:
            proj_objs = Project.objects.filter(
                workspace_id=pk, project_type=project_type
            )
        proj_objs_languages = Project.objects.filter(
            workspace_id=pk, project_type=project_type
        )

        languages = list(set([proj.tgt_language for proj in proj_objs_languages]))

        final_result = []

        for period in range(len(periodical_list) - 1):
            start_end_date = (
                str(periodical_list[period].date())
                + "  To "
                + str(
                    (periodical_list[period + 1].date() - pd.DateOffset(hours=1)).date()
                )
            )
            period_name = ""
            if periodical_type == "weekly":
                period_name = "week_number"
            elif periodical_type == "monthly":
                period_name = "month_number"
            elif periodical_type == "yearly":
                period_name = "year_number"

            data = []
            other_lang = []
            for lang in languages:
                proj_lang_filter = proj_objs.filter(tgt_language=lang)
                annotated_labeled_tasks_count = 0
                if reviewer_reports == True:
                    tasks = Task.objects.filter(
                        project_id__in=proj_lang_filter,
                        task_status__in=[
                            "reviewed",
                            "exported",
                            "super_checked",
                        ],
                    )
                    labeled_count_tasks_ids = list(tasks.values_list("id", flat=True))
                    annotated_labeled_tasks_count = (
                        Annotation.objects.filter(
                            task_id__in=labeled_count_tasks_ids,
                            annotation_type=REVIEWER_ANNOTATION,
                            updated_at__gte=periodical_list[period],
                            updated_at__lt=periodical_list[period + 1],
                        )
                        .exclude(annotation_status="to_be_revised")
                        .count()
                    )
                elif supercheck_reports == True:
                    tasks = Task.objects.filter(
                        project_id__in=proj_lang_filter,
                        task_status__in=[
                            "super_checked",
                        ],
                    )
                    labeled_count_tasks_ids = list(tasks.values_list("id", flat=True))
                    annotated_labeled_tasks_count = Annotation.objects.filter(
                        task_id__in=labeled_count_tasks_ids,
                        annotation_type=SUPER_CHECKER_ANNOTATION,
                        updated_at__gte=periodical_list[period],
                        updated_at__lt=periodical_list[period + 1],
                    ).count()
                else:
                    tasks = Task.objects.filter(
                        project_id__in=proj_lang_filter,
                        task_status__in=[
                            "annotated",
                            "reviewed",
                            "exported",
                            "super_checked",
                        ],
                    )

                    labeled_count_tasks_ids = list(tasks.values_list("id", flat=True))
                    annotated_labeled_tasks_count = Annotation.objects.filter(
                        task_id__in=labeled_count_tasks_ids,
                        annotation_type=ANNOTATOR_ANNOTATION,
                        updated_at__gte=periodical_list[period],
                        updated_at__lt=periodical_list[period + 1],
                    ).count()

                if metainfo == True:
                    result = {}

                    if project_type in get_audio_project_types():
                        total_rev_duration_list = []
                        total_ann_duration_list = []
                        total_sup_duration_list = []

                        for each_task in tasks:
                            if reviewer_reports == True:
                                try:
                                    if each_task.task_status == "reviewed":
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=REVIEWER_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    elif each_task.task_status == "super_checked":
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=SUPER_CHECKER_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    else:
                                        anno = Annotation.objects.filter(
                                            id=each_task.correct_annotation.id,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    total_rev_duration_list.append(
                                        get_audio_transcription_duration(anno.result)
                                    )
                                except:
                                    pass
                            elif supercheck_reports == True:
                                try:
                                    if each_task.task_status == "super_checked":
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=SUPER_CHECKER_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    else:
                                        anno = Annotation.objects.filter(
                                            id=each_task.correct_annotation.id,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    total_sup_duration_list.append(
                                        get_audio_transcription_duration(anno.result)
                                    )
                                except:
                                    pass
                            else:
                                try:
                                    if each_task.task_status == "reviewed":
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=REVIEWER_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    elif each_task.task_status == "exported":
                                        anno = Annotation.objects.filter(
                                            id=each_task.correct_annotation.id,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    elif each_task.task_status == "super_checked":
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=SUPER_CHECKER_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    else:
                                        anno = Annotation.objects.filter(
                                            task=each_task,
                                            annotation_type=ANNOTATOR_ANNOTATION,
                                            updated_at__gte=periodical_list[period],
                                            updated_at__lt=periodical_list[period + 1],
                                        )[0]
                                    total_ann_duration_list.append(
                                        get_audio_transcription_duration(anno.result)
                                    )
                                except:
                                    pass
                        if reviewer_reports == True:
                            rev_total_duration = sum(total_rev_duration_list)
                            rev_total_time = convert_seconds_to_hours(
                                rev_total_duration
                            )
                            result = {
                                "language": lang,
                                "periodical_aud_duration": rev_total_time,
                            }
                        elif supercheck_reports == True:
                            sup_total_duration = sum(total_sup_duration_list)
                            sup_total_time = convert_seconds_to_hours(
                                sup_total_duration
                            )
                            result = {
                                "language": lang,
                                "periodical_aud_duration": sup_total_time,
                            }
                        else:
                            ann_total_duration = sum(total_ann_duration_list)
                            ann_total_time = convert_seconds_to_hours(
                                ann_total_duration
                            )
                            result = {
                                "language": lang,
                                "periodical_aud_duration": ann_total_time,
                            }
                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        total_rev_word_count_list = []
                        total_ann_word_count_list = []
                        total_sup_word_count_list = []

                        if reviewer_reports == True:
                            annotated_labeled_tasks = Annotation.objects.filter(
                                task_id__in=labeled_count_tasks_ids,
                                annotation_type=REVIEWER_ANNOTATION,
                                updated_at__gte=periodical_list[period],
                                updated_at__lt=periodical_list[period + 1],
                            )
                            for each_task in annotated_labeled_tasks:
                                try:
                                    total_rev_word_count_list.append(
                                        each_task.task.data["word_count"]
                                    )
                                except:
                                    pass
                            result = {
                                "language": lang,
                                "periodical_word_count": sum(total_rev_word_count_list),
                            }
                        elif supercheck_reports == True:
                            annotated_labeled_tasks = Annotation.objects.filter(
                                task_id__in=labeled_count_tasks_ids,
                                annotation_type=SUPER_CHECKER_ANNOTATION,
                                updated_at__gte=periodical_list[period],
                                updated_at__lt=periodical_list[period + 1],
                            )
                            for each_task in annotated_labeled_tasks:
                                try:
                                    total_sup_word_count_list.append(
                                        each_task.task.data["word_count"]
                                    )
                                except:
                                    pass
                            result = {
                                "language": lang,
                                "periodical_word_count": sum(total_sup_word_count_list),
                            }
                        else:
                            annotated_labeled_tasks = Annotation.objects.filter(
                                task_id__in=labeled_count_tasks_ids,
                                annotation_type=ANNOTATOR_ANNOTATION,
                                updated_at__gte=periodical_list[period],
                                updated_at__lt=periodical_list[period + 1],
                            )
                            for each_task in annotated_labeled_tasks:
                                try:
                                    total_ann_word_count_list.append(
                                        each_task.task.data["word_count"]
                                    )
                                except:
                                    pass
                            result = {
                                "language": lang,
                                "periodical_word_count": sum(total_ann_word_count_list),
                            }
                else:
                    result = {
                        "language": lang,
                        "periodical_tasks_count": annotated_labeled_tasks_count,
                    }

                if lang == None or lang == "":
                    other_lang.append(result)
                else:
                    data.append(result)

            other_count = 0
            other_word_count = 0
            other_aud_dur = 0
            for dat in other_lang:
                if metainfo != True:
                    other_count += dat["periodical_tasks_count"]
                else:
                    if project_type in get_audio_project_types():
                        other_aud_dur += convert_hours_to_seconds(
                            dat["periodical_aud_duration"]
                        )
                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        other_word_count += dat["periodical_word_count"]

            if len(other_lang) > 0:
                if metainfo != True:
                    other_language = {
                        "language": "Others",
                        "periodical_tasks_count": other_count,
                    }
                else:
                    if project_type in get_audio_project_types():
                        other_language = {
                            "language": "Others",
                            "periodical_aud_duration": convert_seconds_to_hours(
                                other_aud_dur
                            ),
                        }
                    elif (
                        project_type in get_translation_dataset_project_types()
                        or "ConversationTranslation" in project_type
                    ):
                        other_language = {
                            "language": "Others",
                            "periodical_word_count": other_word_count,
                        }

                data.append(other_language)

            try:
                period_result = sorted(data, key=lambda x: x["language"], reverse=False)
            except:
                period_result = []

            if metainfo == True and not (
                (project_type in get_audio_project_types())
                or (
                    project_type in get_translation_dataset_project_types()
                    or "ConversationTranslation" in project_type
                )
            ):
                period_result = []

            summary_period = {
                period_name: period + 1,
                "date_range": start_end_date,
                "data": period_result,
            }

            final_result.append(summary_period)
        return Response(final_result)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER),
                "project_type": openapi.Schema(type=openapi.TYPE_STRING),
                "participation_types": openapi.Schema(
                    type=openapi.TYPE_ARRAY,
                    items=openapi.Items(type=openapi.TYPE_INTEGER),
                ),
            },
            required=["user_id", "project_type", "participation_types"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the Workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: "Email successfully scheduled",
            400: "Invalid request body parameters.",
            401: "Unauthorized access.",
            404: "Workspace/User not found.",
        },
    )
    @action(
        detail=True,
        methods=["POST"],
        name="Get Workspace level users analytics (e-mail)",
        url_name="send_user_analytics",
    )
    def send_user_analytics(self, request, pk=None):
        if not (
            request.user.is_authenticated
            and (
                request.user.role == User.ORGANIZATION_OWNER
                or request.user.role == User.WORKSPACE_MANAGER
                or request.user.is_superuser
            )
        ):
            final_response = {
                "message": "You do not have enough permissions to access this view!"
            }
            return Response(final_response, status=status.HTTP_401_UNAUTHORIZED)

        try:
            workspace = Workspace.objects.get(pk=pk)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )

        user_id = request.data.get("user_id")
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        participation_types = request.data.get("participation_types")
        if len(participation_types) == 0 or not set(participation_types).issubset(
            {1, 2, 3, 4}
        ):
            return Response(
                {"message": "Invalid participation types"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from_date = None
        to_date = None

        if "from_date" in dict(request.data) and "to_date" in dict(request.data):
            from_date = request.data.get("from_date")
            to_date = request.data.get("to_date")
            result_from, invalid_message = is_valid_date(from_date)
            result_to, invalid_message = is_valid_date(to_date)
            if not result_from or not result_to:
                return Response(
                    {"message": invalid_message}, status=status.HTTP_400_BAD_REQUEST
                )
            start_date = datetime.strptime(from_date, "%Y-%m-%d")
            end_date = datetime.strptime(to_date, "%Y-%m-%d")

            if start_date > end_date:
                return Response(
                    {"message": "'To' Date should be after 'From' Date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        project_type = request.data.get("project_type")

        send_user_reports_mail_ws.delay(
            ws_id=workspace.id,
            user_id=user_id,
            project_type=project_type,
            participation_types=participation_types,
            start_date=from_date,
            end_date=to_date,
        )

        return Response(
            {"message": "Email scheduled successfully"}, status=status.HTTP_200_OK
        )


class WorkspaceusersViewSet(viewsets.ViewSet):
    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    description="String containing emails separated by commas",
                )
            },
            required=["user_id"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: "Users added Successfully",
            403: "Not authorized",
            400: "No valid user_ids found",
            404: "Workspace not found",
            500: "Server error occured",
        },
    )
    @permission_classes((IsAuthenticated,))
    @action(
        detail=True, methods=["POST"], url_path="addmembers", url_name="add_members"
    )
    @is_particular_workspace_manager
    def add_members(self, request, pk=None):
        user_id = request.data.get("user_id", "")
        try:
            workspace = Workspace.objects.get(pk=pk)

            if (
                (
                    (request.user.role) == (User.ORGANIZATION_OWNER)
                    and (request.user.organization) == (workspace.organization)
                )
                or (
                    (request.user.role == User.WORKSPACE_MANAGER)
                    and (request.user in workspace.managers.all())
                )
                or (request.user.is_superuser)
            ) == False:
                return Response(
                    {"message": "Not authorized!"}, status=status.HTTP_403_FORBIDDEN
                )
            user_ids = user_id.split(",")
            invalid_user_ids = []
            for user_id in user_ids:
                try:
                    user = User.objects.get(pk=user_id)
                    if (user.organization) == (workspace.organization):
                        workspace.members.add(user)
                    else:
                        invalid_user_ids.append(user_id)
                except User.DoesNotExist:
                    invalid_user_ids.append(user_id)
            workspace.save()
            if len(invalid_user_ids) == 0:
                return Response(
                    {"message": "users added successfully"}, status=status.HTTP_200_OK
                )
            elif len(invalid_user_ids) == len(user_ids):
                return Response(
                    {"message": "No valid user_ids found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    "message": f"users added partially! Invalid user_ids: {','.join(invalid_user_ids)}"
                },
                status=status.HTTP_200_OK,
            )
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"message": "Server Error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_STRING, format="email")
            },
            required=["user_id"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: "User removed Successfully",
            403: "Not authorized",
            404: "Workspace not found/User not in the workspace/User not found",
            500: "Server error occured",
        },
    )
    @permission_classes((IsAuthenticated,))
    @action(
        detail=True,
        methods=["POST"],
        url_path="removemembers",
        url_name="remove_members",
    )
    @is_particular_workspace_manager
    def remove_members(self, request, pk=None):
        user_id = request.data.get("user_id", "")
        try:
            workspace = Workspace.objects.get(pk=pk)

            if (
                (
                    (request.user.role) == (User.ORGANIZATION_OWNER)
                    and (request.user.organization) == (workspace.organization)
                )
                or (
                    (request.user.role == User.WORKSPACE_MANAGER)
                    and (request.user in workspace.managers.all())
                )
                or (request.user.is_superuser)
            ) == False:
                return Response(
                    {"message": "Not authorized!"}, status=status.HTTP_403_FORBIDDEN
                )
            try:
                user = User.objects.get(pk=user_id)
                project_viewset = ProjectViewSet()

                if user in workspace.frozen_users.all():
                    return Response(
                        {"message": "User is already frozen"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if user in workspace.members.all():
                    request.data["ids"] = [
                        user_id
                    ]  # 'ids' key is used in remove_annotator and remove_reviewer functions

                    annotation_projects = Project.objects.filter(
                        annotators__in=[user_id]
                    )
                    for annotation_project in annotation_projects:
                        pk = annotation_project.id
                        response = project_viewset.remove_annotator(
                            request, pk=pk, freeze_user=False
                        )

                    reviewer_projects = Project.objects.filter(
                        annotation_reviewers__in=[user_id]
                    )
                    for reviewer_project in reviewer_projects:
                        pk = reviewer_project.id
                        response = project_viewset.remove_reviewer(
                            request, pk=pk, freeze_user=False
                        )

                    superchecker_projects = Project.objects.filter(
                        review_supercheckers__in=[user_id]
                    )
                    for superchecker_project in superchecker_projects:
                        pk = superchecker_project.id
                        response = project_viewset.remove_superchecker(
                            request, pk=pk, freeze_user=False
                        )

                    for project in (
                        annotation_projects | reviewer_projects | superchecker_projects
                    ).distinct():
                        project.frozen_users.add(user)
                        project.save()

                    workspace.frozen_users.add(user)
                    # workspace.members.remove(user)
                    return Response(
                        {"message": "User removed successfully"},
                        status=status.HTTP_200_OK,
                    )
                else:
                    return Response(
                        {"message": "User not in workspace"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            except User.DoesNotExist:
                return Response(
                    {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"message": "Server Error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_STRING, format="email")
            },
            required=["user_id"],
        ),
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: "Frozen User removed from the workspace",
            400: "User not a frozen user of the workspace",
            403: "Not authorized",
            404: "Workspace not found",
            500: "Server error",
        },
    )
    @permission_classes((IsAuthenticated,))
    @action(detail=True, methods=["post"], url_name="remove_frozen_user")
    @is_particular_workspace_manager
    def remove_frozen_user(self, request, pk=None):
        if "user_id" in dict(request.data):
            user_id = request.data.get("user_id", "")
        else:
            return Response(
                {"message": "key does not match"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            workspace = Workspace.objects.filter(pk=pk).first()
            if not workspace:
                return Response(
                    {"message": "Workspace does not exist"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            user = User.objects.get(pk=user_id)
            if user in workspace.frozen_users.all():
                workspace.frozen_users.remove(user)
                workspace.save()
                return Response(
                    {"message": "Frozen User removed from the workspace"},
                    status=status.HTTP_200_OK,
                )
            else:
                return Response(
                    {"message": "User is not frozen"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except User.DoesNotExist:
            return Response(
                {"message": "User does not exist"}, status=status.HTTP_404_NOT_FOUND
            )
        except ValueError:
            return Response(
                {"message": "Server Error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @swagger_auto_schema(
        method="get",
        manual_parameters=[
            openapi.Parameter(
                "id",
                openapi.IN_PATH,
                description=("A unique integer identifying the workspace"),
                type=openapi.TYPE_INTEGER,
                required=True,
            )
        ],
        responses={
            200: UserFetchSerializer(many=True),
            403: "Not authorized",
            404: "Workspace not found/User not in the workspace/User not found",
            500: "Server error occured",
        },
    )
    @action(
        detail=True, methods=["GET"], url_path="list-managers", url_name="list_managers"
    )
    def list_managers(self, request, pk):
        try:
            workspace = Workspace.objects.get(pk=pk)
            managers = workspace.managers.all()
            user_serializer = UserFetchSerializer(managers, many=True)
            return Response(user_serializer.data)
        except Workspace.DoesNotExist:
            return Response(
                {"message": "Workspace not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print("the exception was ", e)
            return Response(
                {"message": "Server Error occured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(
        detail=False,
        methods=["GET"],
        url_path="user-workspaces/loggedin-user-workspaces",
        url_name="loggedin_user_workspaces",
    )
    def loggedin_user_workspaces(self, request):
        if request.user.is_anonymous:
            return Response({"message": "Access Denied."})
        workspaces = Workspace.objects.filter(members__in=[request.user.pk])
        workspaces_serializer = WorkspaceNameSerializer(workspaces, many=True)
        return Response(workspaces_serializer.data)
