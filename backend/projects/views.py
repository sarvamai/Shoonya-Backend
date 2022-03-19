import re
import random
from urllib.parse import parse_qsl
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django.core.mail import send_mail
from django.conf import settings

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

from users.models import User
from dataset import models as dataset_models
from tasks.models import Task
from .registry_helper import ProjectRegistry

from .serializers import ProjectSerializer, ProjectUsersSerializer
from .models import *
from .decorators import is_organization_owner_or_workspace_manager, project_is_archived, is_particular_workspace_manager, project_is_published
from filters import filter

# Create your views here.

EMAIL_REGEX = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

PROJECT_IS_PUBLISHED_ERROR = {
    'message': 'This project is already published!'
}

def get_task_field(annotation_json, field):
    return annotation_json[field]


class ProjectViewSet(viewsets.ModelViewSet):
    """
    Project ViewSet
    """
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer
    permission_classes = (IsAuthenticatedOrReadOnly, )

    def retrieve(self, request, pk, *args, **kwargs):
        """
        Retrieves a project given its ID
        """
        print(pk)
        return super().retrieve(request, *args, **kwargs)

    @is_organization_owner_or_workspace_manager    
    def create(self, request, *args, **kwargs):
        """
        Creates a project

        Authenticated only for organization owner or workspace manager
        """
        # Read project details from api request
        project_type_key = request.data.get('project_type')
        project_type = dict(PROJECT_TYPE_CHOICES)[project_type_key]
        dataset_instance_ids = request.data.get('dataset_id')
        filter_string = request.data.get('filter_string')
        sampling_mode = request.data.get('sampling_mode')
        sampling_parameters = request.data.get('sampling_parameters_json')
        variable_parameters = request.data.get('variable_parameters')
        
        # Load the dataset model from the instance id using the project registry
        registry_helper = ProjectRegistry.get_instance()
        input_dataset_info = registry_helper.get_input_dataset_and_fields(project_type)
        output_dataset_info = registry_helper.get_output_dataset_and_fields(project_type)

        dataset_model = getattr(dataset_models, input_dataset_info["dataset_type"])
        
        # Get items corresponding to the instance id
        data_items = dataset_model.objects.filter(instance_id__in=dataset_instance_ids)

        print("Samples before filter", data_items)
        
        # Apply filtering
        query_params = dict(parse_qsl(filter_string))
        query_params = filter.fix_booleans_in_dict(query_params)
        filtered_items = filter.filter_using_dict_and_queryset(query_params, data_items)

        # Get the input dataset fields from the filtered items
        filtered_items = list(filtered_items.values('data_id', *input_dataset_info["fields"]))

        print("Samples before smpling", filtered_items)


        # Apply sampling
        if sampling_mode == RANDOM:
            try:
                sampling_count = sampling_parameters['count']
            except KeyError:
                sampling_fraction = sampling_parameters['fraction']
                sampling_count = int(sampling_fraction * len(filtered_items))
            
            sampled_items = random.sample(filtered_items, k=sampling_count)
        elif sampling_mode == BATCH:
            batch_size = sampling_parameters['batch_size']
            try:
                batch_number = sampling_parameters['batch_number']
            except KeyError:
                batch_number = 1
            sampled_items = filtered_items[batch_size*(batch_number-1):batch_size*(batch_number)]
        else:
            sampled_items = filtered_items
        
        print("Samples after sampling", sampled_items)
        
        # Create project object
        project_response = super().create(request, *args, **kwargs)
        project_id = project_response.data["id"]
        project = Project.objects.get(pk=project_id)

        # Set the labelstudio label config
        label_config = registry_helper.get_label_studio_jsx_payload(project_type)
        print(label_config)
        project.label_config = label_config
        project.save()

        # Create task objects
        tasks = []
        for item in sampled_items:
            data_id = item['data_id']
            print("Item before", item)
            try:
                for var_param in output_dataset_info['fields']['variable_parameters']:
                    item[var_param] = variable_parameters[var_param]
            except KeyError:
                pass
            try:
                for input_field, output_field in output_dataset_info['fields']['copy_from_input'].items():
                    item[output_field] = item[input_field]
                    del item[input_field]
            except KeyError:
                pass
            data = dataset_models.DatasetBase.objects.get(pk=data_id)
            # Remove data id because it's not needed in task.data
            del item['data_id']
            print("Item after", item)
            task = Task(
                data=item,
                project_id=project,
                data_id = data
            )
            tasks.append(task)
        
        # Bulk create the tasks
        Task.objects.bulk_create(tasks)
        print("Tasks created")

        # Return the project response
        return project_response


    @is_particular_workspace_manager
    @project_is_archived
    def update(self, request, pk=None, *args, **kwargs):
        '''
        Update project details
        '''
        return super().update(request, *args, **kwargs)        
    
    @is_particular_workspace_manager
    @project_is_archived
    def partial_update(self, request, pk=None, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)
    
    @is_organization_owner_or_workspace_manager    
    @project_is_published
    def destroy(self, request, pk=None, *args, **kwargs):
        '''
        Delete a project
        '''
        return super().delete(request, *args, **kwargs)
    
    # TODO : add exceptions
    @action(detail=True, methods=['POST', 'GET'], name='Archive Project')
    @is_particular_workspace_manager
    def archive(self, request, pk=None, *args, **kwargs):
        '''
        Archive a published project
        '''
        print(pk)
        project = Project.objects.get(pk=pk)
        project.is_archived = not project.is_archived
        project.save()
        return super().retrieve(request, *args, **kwargs)
    
    @action(detail=True, methods=['GET'], name="Get Project Users", url_name='get_project_users')
    @project_is_archived
    def get_project_users(self, request, pk=None, *args, **kwargs):
        '''
        Get the list of annotators in the project
        '''
        ret_dict = {}
        ret_status = 0
        try:
            project = Project.objects.get(pk=pk)
            serializer = ProjectUsersSerializer(project, many=False)
            ret_dict = serializer.data
            ret_status = status.HTTP_200_OK
        except Project.DoesNotExist:
            ret_dict = {"message": "Project does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        return Response(ret_dict, status=ret_status)
    
    @action(detail=True, methods=['POST'], name="Add Project Users", url_name="add_project_users")
    @project_is_archived
    @is_particular_workspace_manager
    def add_project_users(self, request, pk=None, *args, **kwargs):
        '''
        Add annotators to the project
        '''
        ret_dict = {}
        ret_status = 0
        try:
            project = Project.objects.get(pk=pk)
            emails = request.data.get('emails')
            for email in emails:
                if re.fullmatch(EMAIL_REGEX, email):
                    user = User.objects.get(email=email)
                    project.users.add(user)
                    project.save()
                else:
                    print("Invalid Email")
            ret_dict = {"message": "Users added!"}
            ret_status = status.HTTP_201_CREATED
        except Project.DoesNotExist:
            ret_dict = {"message": "Project does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        except User.DoesNotExist:
            ret_dict = {"message": "User does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        return Response(ret_dict, status=ret_status)
    
    @action(detail=False, methods=['GET'], name="Get Project Types", url_name="get_project_types")
    @project_is_archived
    @is_organization_owner_or_workspace_manager
    def get_project_types(self, request, *args, **kwargs):
        project_registry = ProjectRegistry()
        try:
            return Response(project_registry.data, status=status.HTTP_200_OK)
        except Exception:
            print(Exception.args)
            return Response({"message": "Error Occured"}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['POST'], name='Export Project')
    @project_is_archived
    @is_organization_owner_or_workspace_manager
    def project_export(self, request, pk=None, *args, **kwargs):
        '''
        Export a project
        '''
        try:
            project = Project.objects.get(pk=pk)
            project_type = dict(PROJECT_TYPE_CHOICES)[project.project_type]
            # Read registry to get output dataset model, and output fields
            registry_helper = ProjectRegistry.get_instance()
            output_dataset_info = registry_helper.get_output_dataset_and_fields(project_type)

            dataset_model = getattr(dataset_models, output_dataset_info["dataset_type"])

            # If save_type is 'in_place'
            if output_dataset_info['save_type'] == 'in_place':
                annotation_fields = output_dataset_info["fields"]["annotations"]
                data_items = []
                tasks = Task.objects.filter(project_id__exact=project)
                for task in tasks:

                    if task.correct_annotation is not None:
                        data_item = dataset_model.objects.get(data_id__exact=task.data_id.data_id)
                        for field in annotation_fields:
                            setattr(data_item, field, get_task_field(task.correct_annotation.result_json, field))
                        data_items.append(data_item)
                # Loop over project tasks and parse annotation json

                # Write json to dataset columns
                dataset_model.objects.bulk_update(data_items, annotation_fields)
            
            # If save_type is 'new_record'
            elif output_dataset_info['save_type'] == 'new_record':
                export_dataset_instance_id = request.data['export_dataset_instance_id']
                export_dataset_instance = dataset_models.DatasetInstance.objects.get(instance_id__exact=export_dataset_instance_id)

                annotation_fields = output_dataset_info["fields"]["annotations"]
                task_annotation_fields = output_dataset_info["fields"]["variable_parameters"] + list(output_dataset_info["fields"]["copy_from_input"].values())

                data_items = []
                tasks = Task.objects.filter(project_id__exact=project)
                for task in tasks:
                    if task.correct_annotation is not None:
                        # data_item = dataset_model.objects.get(data_id__exact=task.data_id.data_id)
                        data_item = dataset_model()
                        for field in annotation_fields:
                            setattr(data_item, field, get_task_field(task.correct_annotation.result_json, field))
                        for field in task_annotation_fields:
                            setattr(data_item, field, task.data[field])

                        data_item.instance_id = export_dataset_instance
                        data_items.append(data_item)
                
                # TODO: implement bulk create if possible (only if non-hacky)
                # dataset_model.objects.bulk_create(data_items)
                # Saving data items to dataset in a loop
                for item in data_items:
                    item.save()
                
            # FIXME: Allow export multiple times
            project.is_archived=True
            project.save()
            ret_dict = {"message": "SUCCESS!"}         
            ret_status = status.HTTP_200_OK
        except Project.DoesNotExist:
            ret_dict = {"message": "Project does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        except User.DoesNotExist:
            ret_dict = {"message": "User does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        return Response(ret_dict, status=ret_status)

    @action(detail=True, methods=['POST', 'GET'], name='Publish Project')
    @project_is_archived
    @is_organization_owner_or_workspace_manager
    def project_publish(self, request, pk=None, *args, **kwargs):
        '''
        Publish a project
        '''
        try:
            project = Project.objects.get(pk=pk)

            if project.is_published:
                return Response(PROJECT_IS_PUBLISHED_ERROR, status=status.HTTP_200_OK)

            serializer = ProjectUsersSerializer(project, many=False)
            #ret_dict = serializer.data
            users = serializer.data['users']
            #print(ret_dict)
           
            project.is_published = True
            project.save()

            for user in users:
                print(user['email'])
                userEmail = user['email']
                
                #send_mail("Annotation Tasks Assigned",
                #f"Hello! You are assigned to tasks in the project {project.title}.",
                #settings.DEFAULT_FROM_EMAIL, [userEmail],
                #)

            ret_dict = {"message": "This project is published"}
            ret_status = status.HTTP_200_OK
        except Project.DoesNotExist:
            ret_dict = {"message": "Project does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        except User.DoesNotExist:
            ret_dict = {"message": "User does not exist!"}
            ret_status = status.HTTP_404_NOT_FOUND
        return Response(ret_dict, status=ret_status)
        

    

 