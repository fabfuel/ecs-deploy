import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class EcsService(dict):
    def __init__(self, cluster, iterable=None, **kwargs):
        self._cluster = cluster
        super(EcsService, self).__init__(iterable, **kwargs)

    def set_desired_count(self, desired_count):
        self['desiredCount'] = desired_count

    def set_task_definition(self, task_definition):
        self['taskDefinition'] = task_definition.arn

    @property
    def cluster(self):
        return self._cluster

    @property
    def name(self):
        return self.get(u'serviceName')

    @property
    def task_definition(self):
        return self.get(u'taskDefinition')

    @property
    def desired_count(self):
        return self.get(u'desiredCount')

    @property
    def deployment_created_at(self):
        for deployment in self.get('deployments'):
            if deployment.get(u'status') == u'PRIMARY':
                return deployment.get(u'createdAt')
        return datetime.now()

    @property
    def deployment_updated_at(self):
        for deployment in self.get('deployments'):
            if deployment.get(u'status') == u'PRIMARY':
                return deployment.get(u'updatedAt')
        return datetime.now()


class EcsTaskDefinition(dict):
    def __init__(self, iterable=None, **kwargs):
        super(EcsTaskDefinition, self).__init__(iterable, **kwargs)
        self._diff = []

    @property
    def containers(self):
        return self.get('containerDefinitions')

    @property
    def volumes(self):
        return self.get('volumes')

    @property
    def arn(self):
        return self.get('taskDefinitionArn')

    @property
    def family(self):
        return self.get('family')

    @property
    def revision(self):
        return self.get('revision')

    @property
    def diff(self):
        return self._diff

    def set_images(self, tag=None, **images):
        for container in self.containers:
            if container['name'] in images:
                new_image = images[container['name']]
                diff = EcsTaskDefinitionDiff(container['name'], 'image', new_image, container['image'])
                self._diff.append(diff)
                container['image'] = new_image
            elif tag:
                image_definition = container['image'].rsplit(':', 1)
                new_image = '%s:%s' % (image_definition[0], tag)
                diff = EcsTaskDefinitionDiff(container['name'], 'image', new_image, container['image'])
                self._diff.append(diff)
                container['image'] = new_image

    def set_commands(self, **commands):
        for container in self.containers:
            if container['name'] in commands:
                new_command = commands[container['name']]
                diff = EcsTaskDefinitionDiff(container['name'], 'command', new_command, container.get('command'))
                self._diff.append(diff)
                container['command'] = [new_command]


class EcsTaskDefinitionDiff(object):
    def __init__(self, container, field, value, old_value):
        self.container = container
        self.field = field
        self.value = value
        self.old_value = old_value

    def __repr__(self):
        return "Changed %s of container '%s' to: %s (was: %s)" % \
               (self.field, self.container, self.value, self.old_value)


class EcsAction(object):
    def __init__(self, cluster, service, access_key_id, secret_access_key, region, profile):
        if profile:
            os.environ['AWS_PROFILE'] = profile
        self._client = boto3.client('ecs', aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key,
                                    region_name=region)
        self._cluster_name = cluster
        self._service_name = service

        try:
            self._service = self.get_service()
        except IndexError:
            raise ConnectionError('An error occurred when calling the DescribeServices operation: Service not found')
        except ClientError as e:
            raise ConnectionError(e.message)
        except NoCredentialsError:
            raise ConnectionError('Unable to locate credentials. Configure credentials by running "aws configure".')

    def get_service(self):
        services_definition = self._client.describe_services(cluster=self._cluster_name, services=[self._service_name])
        return EcsService(self._cluster_name, services_definition['services'][0])

    def get_current_task_definition(self):
        task_definition = self._client.describe_task_definition(taskDefinition=self._service.task_definition)
        task_definition = EcsTaskDefinition(task_definition['taskDefinition'])
        return task_definition

    def update_task_definition(self, task_definition):
        response_register = self._client.register_task_definition(
            family=task_definition.family,
            containerDefinitions=task_definition.containers,
            volumes=task_definition.volumes)
        new_task_definition = EcsTaskDefinition(response_register['taskDefinition'])
        self._client.deregister_task_definition(taskDefinition=task_definition.arn)
        return new_task_definition

    def update_service(self, service):
        response = self._client.update_service(
            cluster=service.cluster,
            service=service.name,
            desiredCount=service.desired_count,
            taskDefinition=service.task_definition
        )
        return EcsService(self._cluster_name, response['service'])

    @property
    def service(self):
        return self._service

    def is_deployed(self):
        running_tasks = self._client.list_tasks(cluster=self._cluster_name, serviceName=self._service_name)

        if not running_tasks['taskArns']:
            return self.service.desired_count == 0

        running_count = 0
        tasks_details = self._client.describe_tasks(cluster=self._cluster_name, tasks=running_tasks['taskArns'])

        for task in tasks_details['tasks']:
            if task['taskDefinitionArn'] == self.service.task_definition and task['lastStatus'] == 'RUNNING':
                running_count += 1

        return running_count == self.service.desired_count


class DeployAction(EcsAction):
    def deploy(self, task_definition):
        self.service.set_task_definition(task_definition)
        return self.update_service(self.service)


class ScaleAction(EcsAction):
    def scale(self, desired_count):
        self.service.set_desired_count(desired_count)
        return self.update_service(self.service)


class ConnectionError(Exception):
    pass
