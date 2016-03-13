from datetime import datetime

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


class EcsClient(object):
    def __init__(self, access_key_id, secret_access_key, region, profile):
        session = boto3.session.Session(aws_access_key_id=access_key_id,
                                        aws_secret_access_key=secret_access_key,
                                        region_name=region,
                                        profile_name=profile)
        self.boto = session.client('ecs')

    def describe_services(self, cluster_name, service_name):
        return self.boto.describe_services(cluster=cluster_name, services=[service_name])

    def describe_task_definition(self, task_definition_arn):
        return self.boto.describe_task_definition(taskDefinition=task_definition_arn)

    def list_tasks(self, cluster_name, service_name):
        return self.boto.list_tasks(cluster=cluster_name, serviceName=service_name)

    def describe_tasks(self, cluster_name, task_arns):
        return self.boto.describe_tasks(cluster=cluster_name, tasks=task_arns)

    def register_task_definition(self, family, containers, volumes):
        return self.boto.register_task_definition(family=family, containerDefinitions=containers, volumes=volumes)

    def deregister_task_definition(self, task_definition_arn):
        return self.boto.deregister_task_definition(taskDefinition=task_definition_arn)

    def update_service(self, cluster, service, desired_count, task_definition):
        return self.boto.update_service(
            cluster=cluster,
            service=service,
            desiredCount=desired_count,
            taskDefinition=task_definition
        )


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
    def container_names(self):
        for container in self.get('containerDefinitions'):
            yield container['name']

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
        self.validate_image_options(**images)
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
        self.validate_image_options(**commands)
        for container in self.containers:
            if container['name'] in commands:
                new_command = commands[container['name']]
                diff = EcsTaskDefinitionDiff(container['name'], 'command', new_command, container.get('command'))
                self._diff.append(diff)
                container['command'] = [new_command]

    def validate_image_options(self, **container_options):
        for container_name in container_options:
            if container_name not in self.container_names:
                raise UnknownContainerError('Unknown container: %s' % container_name)


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
        self._client = EcsClient(access_key_id, secret_access_key, region, profile)
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
        services_definition = self._client.describe_services(self._cluster_name, self._service_name)
        return EcsService(self._cluster_name, services_definition['services'][0])

    def get_current_task_definition(self):
        task_definition = self._client.describe_task_definition(self._service.task_definition)
        task_definition = EcsTaskDefinition(task_definition['taskDefinition'])
        return task_definition

    def update_task_definition(self, task_definition):
        response = self._client.register_task_definition(task_definition.family, task_definition.containers,
                                                         task_definition.volumes)
        new_task_definition = EcsTaskDefinition(response['taskDefinition'])
        self._client.deregister_task_definition(task_definition.arn)
        return new_task_definition

    def update_service(self, service):
        response = self._client.update_service(service.cluster, service.name, service.desired_count, service.task_definition)
        return EcsService(self._cluster_name, response['service'])

    def is_deployed(self):
        running_tasks = self._client.list_tasks(self._cluster_name, self._service_name)
        if not running_tasks['taskArns']:
            return self._service.desired_count == 0
        return self._service.desired_count == self.get_running_tasks_count(running_tasks['taskArns'])

    def get_running_tasks_count(self, task_arns):
        running_count = 0
        tasks_details = self._client.describe_tasks(self._cluster_name, task_arns)
        for task in tasks_details['tasks']:
            if task['taskDefinitionArn'] == self._service.task_definition and task['lastStatus'] == 'RUNNING':
                running_count += 1
        return running_count


class DeployAction(EcsAction):
    def deploy(self, task_definition):
        self._service.set_task_definition(task_definition)
        return self.update_service(self._service)


class ScaleAction(EcsAction):
    def scale(self, desired_count):
        self._service.set_desired_count(desired_count)
        return self.update_service(self._service)


class EcsError(Exception):
    pass


class ConnectionError(EcsError):
    pass


class UnknownContainerError(EcsError):
    pass
