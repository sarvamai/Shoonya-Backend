from http.client import responses
import secrets
import string
from wsgiref.util import request_uri
from rest_framework import viewsets, status
import re
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import permission_classes
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from .serializers import (
    UserProfileSerializer,
    UserSignUpSerializer,
    UserUpdateSerializer,
    LanguageSerializer,
)
from organizations.models import Invite, Organization
from organizations.serializers import InviteGenerationSerializer
from organizations.decorators import is_organization_owner
from users.models import LANG_CHOICES, User
from rest_framework.decorators import action
from tasks.models import Task
from workspaces.models import Workspace
from projects.models import Project
from tasks.models import Annotation
from organizations.models import Organization
from django.db.models import Q
from projects.utils import no_of_words, is_valid_date
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail


regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"


def generate_random_string(length=12):
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for i in range(length)
    )


class InviteViewSet(viewsets.ViewSet):
    @swagger_auto_schema(request_body=InviteGenerationSerializer)
    @permission_classes((IsAuthenticated,))
    @is_organization_owner
    @action(
        detail=False, methods=["post"], url_path="generate", url_name="invite_users"
    )
    def invite_users(self, request):
        """
        Invite users to join your organization. This generates a new invite
        with an invite code or adds users to an existing one.
        """
        emails = request.data.get("emails")
        organization_id = request.data.get("organization_id")
        users = []
        try:
            org = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        valid_user_emails = []
        invalid_emails = []
        try:
            org = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            return Response(
                {"message": "Organization not found"}, status=status.HTTP_404_NOT_FOUND
            )
        for email in emails:
            # Checking if the email is in valid format.
            if re.fullmatch(regex, email):
                try:
                    user = User(
                        username=generate_random_string(12),
                        email=email,
                        organization_id=org.id,
                        role=request.data.get("role"),
                    )
                    user.set_password(generate_random_string(10))
                    valid_user_emails.append(email)
                    users.append(user)
                except:
                    pass
            else:
                invalid_emails.append(email)
        if len(valid_user_emails) <= 0:
            return Response(
                {"message": "No valid emails found"}, status=status.HTTP_400_BAD_REQUEST
            )
        if len(invalid_emails) == 0:
            ret_dict = {"message": "Invites sent"}
            ret_status = status.HTTP_201_CREATED
        else:
            ret_dict = {
                "message": f"Invites sent partially! Invalid emails: {','.join(invalid_emails)}"
            }
            ret_status = status.HTTP_201_CREATED

        users = User.objects.bulk_create(users)

        Invite.create_invite(organization=org, users=users)
        return Response(ret_dict, status=status.HTTP_200_OK)

    @permission_classes([AllowAny])
    @swagger_auto_schema(request_body=UserSignUpSerializer)
    @action(detail=True, methods=["patch"], url_path="accept", url_name="sign_up_user")
    def sign_up_user(self, request, pk=None):
        """
        Users to sign up for the first time.
        """
        email = request.data.get("email")
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if user.has_accepted_invite:
            return Response(
                {"message": "User has already accepted invite"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            Invite.objects.get(user=user, invite_code=pk)
        except Invite.DoesNotExist:
            return Response(
                {"message": "Invite not found"}, status=status.HTTP_404_NOT_FOUND
            )

        serialized = UserSignUpSerializer(user, request.data, partial=True)
        if serialized.is_valid():
            serialized.save()
            return Response({"message": "User signed up"}, status=status.HTTP_200_OK)


class UserViewSet(viewsets.ViewSet):
    permission_classes = (IsAuthenticated,)

    @swagger_auto_schema(request_body=UserUpdateSerializer)
    @action(detail=False, methods=["patch"], url_path="update", url_name="edit_profile")
    def edit_profile(self, request):
        """
        Updating user profile.
        """
        user = request.user
        serialized = UserUpdateSerializer(user, request.data, partial=True)
        if serialized.is_valid():
            serialized.save()
            return Response(
                {"message": "User profile edited"}, status=status.HTTP_200_OK
            )

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    @action(detail=False, methods=["get"], url_path="me/fetch")
    def fetch_profile(self, request):
        """
        Fetches profile for logged in user
        """
        serialized = UserProfileSerializer(request.user)
        return Response(serialized.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(responses={200: UserProfileSerializer})
    @action(detail=True, methods=["get"], url_path="fetch")
    def fetch_other_profile(self, request, pk=None):
        """
        Fetches profile for any user
        """
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        if user.organization_id is not request.user.organization_id:
            return Response(
                {"message": "Not Authorized"}, status=status.HTTP_403_FORBIDDEN
            )
        serialized = UserProfileSerializer(user)
        return Response(serialized.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "email": openapi.Schema(
                    type=openapi.TYPE_STRING, format="email", description="New email"
                )
            },
            required=["email"],
        ),
        responses={
            200: "Verification email sent to both of your email ids.Please verify to update your email",
            403: "Please enter a valid email!",
        },
    )
    @action(
        detail=False, methods=["post"], url_path="update_email", url_name="update_email"
    )
    def update_email(self, request):
        """
        Updates the User Email
        """
        try:
            user = request.user
            unverified_email = request.data.get("email")

            old_email_update_code = generate_random_string(10)
            new_email_verification_code = generate_random_string(10)

            send_mail(
                "Email Verification",
                f"Your email verification code is:{old_email_update_code}",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
            )

            send_mail(
                "Email Verification",
                f"Your email verification code is:{new_email_verification_code}",
                settings.DEFAULT_FROM_EMAIL,
                [unverified_email],
            )

            user.unverified_email = unverified_email
            user.old_email_update_code = old_email_update_code
            user.new_email_verification_code = new_email_verification_code
            user.save()

            return Response(
                {
                    "message": "Verification email sent to both of your email ids.Please verify to update your email"
                },
                status=status.HTTP_200_OK,
            )
        except:
            return Response(
                {"message": "Please enter a valid email!"},
                status=status.HTTP_403_FORBIDDEN,
            )

    @swagger_auto_schema(
        method="post",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "old_email_update_code": openapi.Schema(type=openapi.TYPE_STRING),
                "new_email_verification_code": openapi.Schema(type=openapi.TYPE_STRING),
            },
            required=["old_email_update_code", "new_email_verification_code"],
        ),
        responses={
            200: "Email verification Successful!",
            403: "Invalid verification codes!",
        },
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="verify_email_updation",
        url_name="verify_email_updation",
    )
    def verify_email_updation(self, request):
        """
        Verify email updation
        """
        user = request.user
        if (user.unverified_email) != "":
            old_email_update_code = request.data.get("old_email_update_code")
            new_email_verification_code = request.data.get(
                "new_email_verification_code"
            )
            if (user.old_email_update_code) == old_email_update_code and (
                user.new_email_verification_code
            ) == new_email_verification_code:
                user.email = user.unverified_email
                user.unverified_email = ""
                user.old_email_update_code = ""
                user.new_email_verification_code = ""
                user.save()
                ret_dict = {"message": "Email verification Successful!"}
                ret_status = status.HTTP_200_OK
            else:
                ret_dict = {"message": "Invalid verification codes!"}
                ret_status = status.HTTP_403_FORBIDDEN
        else:
            ret_dict = {"message": "Invalid verification codes!"}
            ret_status = status.HTTP_403_FORBIDDEN

        return Response(ret_dict, status=ret_status)


class AnalyticsViewSet(viewsets.ViewSet):
    permission_classes = (AllowAny,)

    @action(
        detail=False,
        methods=["POST"],
        url_path="user_analytics",
        url_name="get_user_analytics",
    )
    def get_user_analytics(self, request):
        """
        Get Reports of a User
        """

        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        user_id = request.data.get("user_id")
        reports_type = request.data.get("reports_type")

        start_date = start_date + " 00:00"
        end_date = end_date + " 23:59"

        cond, invalid_message = is_valid_date(start_date)
        if not cond:
            return Response(
                {"message": invalid_message}, status=status.HTTP_400_BAD_REQUEST
            )

        cond, invalid_message = is_valid_date(end_date)
        if not cond:
            return Response(
                {"message": invalid_message}, status=status.HTTP_400_BAD_REQUEST
            )

        start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M")
        end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M")

        if start_date > end_date:
            return Response(
                {"message": "'To' Date should be after 'From' Date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        project_type = request.data.get("project_type")
        project_type_lower = project_type.lower()
        is_translation_project = True if "translation" in project_type_lower else False

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"message": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

        project_objs = Project.objects.filter(
            annotators=user_id,
            project_type=project_type,
        )

        all_annotated_lead_time_list = []
        all_annotated_lead_time_count = 0
        total_annotated_tasks_count = 0
        all_tasks_word_count = 0

        project_wise_summary = []
        for proj in project_objs:

            project_name = proj.title
            labeld_tasks_objs = Task.objects.filter(
                Q(project_id=proj.id)
                & Q(annotation_users=user_id)
                & Q(
                    task_status__in=[
                        "accepted",
                        "to_be_revised",
                        "accepted_with_changes",
                        "labeled",
                    ]
                )
            )

            annotated_task_ids = list(labeld_tasks_objs.values_list("id", flat=True))
            annotated_labeled_tasks = Annotation.objects.filter(
                task_id__in=annotated_task_ids,
                parent_annotation_id=None,
                created_at__range=[start_date, end_date],
                completed_by=user_id,
            )

            annotated_tasks_count = annotated_labeled_tasks.count()
            total_annotated_tasks_count += annotated_tasks_count

            avg_lead_time = 0
            lead_time_annotated_tasks = [
                eachtask.lead_time for eachtask in annotated_labeled_tasks
            ]
            all_annotated_lead_time_list.extend(lead_time_annotated_tasks)
            if len(lead_time_annotated_tasks) > 0:
                avg_lead_time = sum(lead_time_annotated_tasks) / len(
                    lead_time_annotated_tasks
                )
                avg_lead_time = round(avg_lead_time, 2)

            total_word_count = 0
            if is_translation_project:
                total_word_count_list = [
                    each_task.task.data["word_count"]
                    for each_task in annotated_labeled_tasks
                ]
                total_word_count = sum(total_word_count_list)
            all_tasks_word_count += total_word_count

            if is_translation_project:
                result = {
                    "Project Name": project_name,
                    "Annotated Tasks": annotated_tasks_count,
                    "Word Count": total_word_count,
                    "Average Annotation Time (In Seconds)": avg_lead_time,
                }
            else:
                result = {
                    "Project Name": project_name,
                    "Annotated Tasks": annotated_tasks_count,
                    "Average Annotation Time (In Seconds)": avg_lead_time,
                }

            project_wise_summary.append(result)

        project_wise_summary = sorted(
            project_wise_summary, key=lambda x: x["Annotated Tasks"], reverse=True
        )

        if total_annotated_tasks_count > 0:
            all_annotated_lead_time_count = (
                sum(all_annotated_lead_time_list) / total_annotated_tasks_count
            )

        total_summary = {}
        if is_translation_project:
            total_summary = {
                "Annotated Tasks": total_annotated_tasks_count,
                "Word Count": all_tasks_word_count,
                "Average Annotation Time (In Seconds)": all_annotated_lead_time_count,
            }

        else:
            total_summary = {
                "Annotated Tasks": total_annotated_tasks_count,
                "Average Annotation Time (In Seconds)": all_annotated_lead_time_count,
            }

        final_result = {
            "total_summary": total_summary,
            "project_summary": project_wise_summary,
        }
        return Response(final_result)


class LanguageViewSet(viewsets.ViewSet):
    permission_classes = (AllowAny,)

    @swagger_auto_schema(responses={200: LanguageSerializer})
    @action(detail=False, methods=["get"], url_path="fetch")
    def fetch_language(self, request):
        """
        Fetches all language choices available to the user.
        """
        serialized = LanguageSerializer(
            data={"language": [lang[0] for lang in LANG_CHOICES]}
        )
        if serialized.is_valid():
            return Response(serialized.data, status=status.HTTP_200_OK)
        return Response(serialized.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
