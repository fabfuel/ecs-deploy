from datetime import datetime
import json
import re

from boto3.session import Session
from botocore.exceptions import ClientError, NoCredentialsError
from dateutil.tz.tz import tzlocal
from dictdiffer import diff

JSON_LIST_REGEX = re.compile(r'^\[.*\]$')

# Python2 raises ValueError
try:
    JSONDecodeError = json.JSONDecodeError
except AttributeError:
    JSONDecodeError = ValueError

LAUNCH_TYPE_EC2 = 'EC2'
LAUNCH_TYPE_FARGATE = 'FARGATE'


def read_env_file(container_name,file):
    env_vars = []
    try:
        with open(file) as f:
            for line in f:
                if line.startswith('#') or not line.strip() or '=' not in line:
                    continue
                key, value = line.strip().split('=', 1)
                env_vars.append((container_name,key,value))
    except Exception as e:
        raise EcsTaskDefinitionCommandError(str(e))
    return tuple(env_vars)


class EcsClient(object):
    def __init__(self, access_key_id=None, secret_access_key=None,
                 region=None, profile=None, session_token=None):
        session = Session(aws_access_key_id=access_key_id,
                          aws_secret_access_key=secret_access_key,
                          aws_session_token=session_token,
                          region_name=region,
                          profile_name=profile)
        self.boto = session.client(u'ecs')
        self.events = session.client(u'events')

    def describe_services(self, cluster_name, service_name):
        return self.boto.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )

    def describe_task_definition(self, task_definition_arn):
        try:
            return self.boto.describe_task_definition(
                taskDefinition=task_definition_arn,
                include=[
                    'TAGS',
                ]
            )
        except ClientError:
            raise UnknownTaskDefinitionError(
                u'Unknown task definition arn: %s' % task_definition_arn
            )

    def list_tasks(self, cluster_name, service_name):
        return self.boto.list_tasks(
            cluster=cluster_name,
            serviceName=service_name
        )

    def describe_tasks(self, cluster_name, task_arns):
        return self.boto.describe_tasks(cluster=cluster_name, tasks=task_arns)

    def register_task_definition(self, family, containers, volumes, role_arn,
                                 execution_role_arn, tags, additional_properties):
        if tags:
            additional_properties['tags'] = tags

        return self.boto.register_task_definition(
            family=family,
            containerDefinitions=containers,
            volumes=volumes,
            taskRoleArn=role_arn,
            executionRoleArn=execution_role_arn,
            **additional_properties
        )

    def deregister_task_definition(self, task_definition_arn):
        return self.boto.deregister_task_definition(
            taskDefinition=task_definition_arn
        )

    def update_service(self, cluster, service, desired_count, task_definition):
        if desired_count is None:
            return self.boto.update_service(
                cluster=cluster,
                service=service,
                taskDefinition=task_definition
            )
        return self.boto.update_service(
            cluster=cluster,
            service=service,
            desiredCount=desired_count,
            taskDefinition=task_definition
        )

    def run_task(self, cluster, task_definition, count, started_by, overrides,
                 launchtype='EC2', subnets=(), security_groups=(),
                 public_ip=False, platform_version=None):

        if launchtype == LAUNCH_TYPE_FARGATE:
            if not subnets or not security_groups:
                msg = 'At least one subnet (--subnet) and one security ' \
                      'group (--securitygroup) definition are required ' \
                      'for launch type FARGATE'
                raise TaskPlacementError(msg)

            network_configuration = {
                "awsvpcConfiguration": {
                    "subnets": subnets,
                    "securityGroups": security_groups,
                    "assignPublicIp": "ENABLED" if public_ip else "DISABLED"
                }
            }

            if platform_version is None:
                platform_version = 'LATEST'

            return self.boto.run_task(
                cluster=cluster,
                taskDefinition=task_definition,
                count=count,
                startedBy=started_by,
                overrides=overrides,
                launchType=launchtype,
                networkConfiguration=network_configuration,
                platformVersion=platform_version,
            )

        return self.boto.run_task(
            cluster=cluster,
            taskDefinition=task_definition,
            count=count,
            startedBy=started_by,
            overrides=overrides
        )

    def update_rule(self, cluster, rule, task_definition):
        target = self.events.list_targets_by_rule(Rule=rule)['Targets'][0]
        target['Arn'] = task_definition.arn.partition('task-definition')[0] + 'cluster/' + cluster
        target['EcsParameters']['TaskDefinitionArn'] = task_definition.arn
        self.events.put_targets(Rule=rule, Targets=[target])
        return target['Id']


class EcsService(dict):
    def __init__(self, cluster, service_definition=None, **kwargs):
        self._cluster = cluster
        super(EcsService, self).__init__(service_definition, **kwargs)

    def set_task_definition(self, task_definition):
        self[u'taskDefinition'] = task_definition.arn

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
        for deployment in self.get(u'deployments'):
            if deployment.get(u'status') == u'PRIMARY':
                return deployment.get(u'createdAt')
        return datetime.now()

    @property
    def deployment_updated_at(self):
        for deployment in self.get(u'deployments'):
            if deployment.get(u'status') == u'PRIMARY':
                return deployment.get(u'updatedAt')
        return datetime.now()

    @property
    def errors(self):
        return self.get_warnings(
            since=self.deployment_updated_at
        )

    @property
    def older_errors(self):
        return self.get_warnings(
            since=self.deployment_created_at,
            until=self.deployment_updated_at
        )

    def get_warnings(self, since=None, until=None):
        since = since or self.deployment_created_at
        until = until or datetime.now(tz=tzlocal())
        errors = {}
        for event in self.get(u'events'):
            if u'unable' not in event[u'message']:
                continue
            if since < event[u'createdAt'] < until:
                errors[event[u'createdAt']] = event[u'message']
        return errors


class EcsTaskDefinition(object):
    def __init__(self, containerDefinitions, volumes, family, revision,
                 status, taskDefinitionArn, requiresAttributes=None,
                 taskRoleArn=None, executionRoleArn=None, compatibilities=None,
                 tags=None, registeredAt=None, registeredBy=None, **kwargs):

        self.containers = containerDefinitions
        self.volumes = volumes
        self.family = family
        self.revision = revision
        self.status = status
        self.arn = taskDefinitionArn
        self.requires_attributes = requiresAttributes or {}
        self.role_arn = taskRoleArn or u''
        self.execution_role_arn = executionRoleArn or u''
        self.tags = tags
        self.additional_properties = kwargs
        self._diff = []

        # the following parameters are returned from the ECS API, when
        # describing a task, but may not be included, when registering a new
        # task definition. Just storing them for now.
        self.compatibilities = compatibilities
        self.registered_at = registeredAt
        self.registered_by = registeredBy

    @property
    def container_names(self):
        for container in self.containers:
            yield container[u'name']

    @property
    def family_revision(self):
        return '%s:%d' % (self.family, self.revision)

    @property
    def diff(self):
        return self._diff

    def diff_raw(self, task_b):
        containers_a = {c['name']: c for c in self.containers}
        containers_b = {c['name']: c for c in task_b.containers}

        requirements_a = sorted([r['name'] for r in self.requires_attributes])
        requirements_b = sorted([r['name'] for r in task_b.requires_attributes])

        for container in containers_a:
            containers_a[container]['environment'] = {e['name']: e['value'] for e in
                                                      containers_a[container].get('environment', {})}

        for container in containers_b:
            containers_b[container]['environment'] = {e['name']: e['value'] for e in
                                                      containers_b[container].get('environment', {})}

        for container in containers_a:
            containers_a[container]['secrets'] = {e['name']: e['valueFrom'] for e in
                                                  containers_a[container].get('secrets', {})}

        for container in containers_b:
            containers_b[container]['secrets'] = {e['name']: e['valueFrom'] for e in
                                                  containers_b[container].get('secrets', {})}

        composite_a = {
            'containers': containers_a,
            'volumes': self.volumes,
            'requires_attributes': requirements_a,
            'role_arn': self.role_arn,
            'execution_role_arn': self.execution_role_arn,
            'compatibilities': self.compatibilities,
            'additional_properties': self.additional_properties,
        }

        composite_b = {
            'containers': containers_b,
            'volumes': task_b.volumes,
            'requires_attributes': requirements_b,
            'role_arn': task_b.role_arn,
            'execution_role_arn': task_b.execution_role_arn,
            'compatibilities': task_b.compatibilities,
            'additional_properties': task_b.additional_properties,
        }

        return list(diff(composite_a, composite_b))

    def get_overrides(self):
        override = dict()
        overrides = []
        for diff in self.diff:
            if override.get('name') != diff.container:
                override = dict(name=diff.container)
                overrides.append(override)
            if diff.field == 'command':
                override['command'] = self.get_overrides_command(diff.value)
            elif diff.field == 'environment':
                override['environment'] = self.get_overrides_env(diff.value)
            elif diff.field == 'secrets':
                override['secrets'] = self.get_overrides_secrets(diff.value)
        return overrides

    @staticmethod
    def parse_command(command):
        if re.match(JSON_LIST_REGEX, command):
            try:
                return json.loads(command)
            except JSONDecodeError as e:
                raise EcsTaskDefinitionCommandError(
                    "command should be valid JSON list. Got following "
                    "command: {} resulting in error: {}"
                        .format(command, str(e)))

        return command.split()

    @staticmethod
    def get_overrides_command(command):
        return EcsTaskDefinition.parse_command(command)

    @staticmethod
    def get_overrides_env(env):
        return [{"name": e, "value": env[e]} for e in env]

    @staticmethod
    def get_overrides_secrets(secrets):
        return [{"name": s, "valueFrom": secrets[s]} for s in secrets]

    def set_images(self, tag=None, **images):
        self.validate_container_options(**images)
        for container in self.containers:
            if container[u'name'] in images:
                new_image = images[container[u'name']]
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'image',
                    value=new_image,
                    old_value=container[u'image']
                )
                self._diff.append(diff)
                container[u'image'] = new_image
            elif tag:
                image_definition = container[u'image'].rsplit(u':', 1)
                new_image = u'%s:%s' % (image_definition[0], tag.strip())
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'image',
                    value=new_image,
                    old_value=container[u'image']
                )
                self._diff.append(diff)
                container[u'image'] = new_image

    def set_commands(self, **commands):
        self.validate_container_options(**commands)
        for container in self.containers:
            if container[u'name'] in commands:
                new_command = commands[container[u'name']]
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'command',
                    value=new_command,
                    old_value=container.get(u'command')
                )
                self._diff.append(diff)
                container[u'command'] = self.parse_command(new_command)

    def set_environment(self, environment_list, exclusive=False, env_file=((None, None),)):
        environment = {}
        if None not in env_file[0]:
            for env in env_file:
                l = read_env_file(env[0], env[1])
                environment_list = l + environment_list
        for env in environment_list:
            environment.setdefault(env[0], {})
            environment[env[0]][env[1]] = env[2]

        self.validate_container_options(**environment)
        for container in self.containers:
            if container[u'name'] in environment:
                self.apply_container_environment(
                    container=container,
                    new_environment=environment[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_environment(
                    container=container,
                    new_environment={},
                    exclusive=exclusive,
                )

    def apply_container_environment(self, container, new_environment, exclusive=False):
        environment = container.get('environment', {})
        old_environment = {env['name']: env['value'] for env in environment}

        if exclusive is True:
            merged = new_environment
        else:
            merged = old_environment.copy()
            merged.update(new_environment)

        if old_environment == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'environment',
            value=merged,
            old_value=old_environment
        )
        self._diff.append(diff)

        container[u'environment'] = [
            {"name": e, "value": merged[e]} for e in merged
        ]

    def set_secrets(self, secrets_list, exclusive=False):
        secrets = {}

        for secret in secrets_list:
            secrets.setdefault(secret[0], {})
            secrets[secret[0]][secret[1]] = secret[2]

        self.validate_container_options(**secrets)
        for container in self.containers:
            if container[u'name'] in secrets:
                self.apply_container_secrets(
                    container=container,
                    new_secrets=secrets[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_secrets(
                    container=container,
                    new_secrets={},
                    exclusive=exclusive,
                )

    def apply_container_secrets(self, container, new_secrets, exclusive=False):
        secrets = container.get('secrets', {})
        old_secrets = {secret['name']: secret['valueFrom'] for secret in secrets}

        if exclusive is True:
            merged = new_secrets
        else:
            merged = old_secrets.copy()
            merged.update(new_secrets)

        if old_secrets == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'secrets',
            value=merged,
            old_value=old_secrets
        )
        self._diff.append(diff)

        container[u'secrets'] = [
            {"name": s, "valueFrom": merged[s]} for s in merged
        ]

    def validate_container_options(self, **container_options):
        for container_name in container_options:
            if container_name not in self.container_names:
                raise UnknownContainerError(
                    u'Unknown container: %s' % container_name
                )

    def set_role_arn(self, role_arn):
        if role_arn:
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'role_arn',
                value=role_arn,
                old_value=self.role_arn
            )
            self.role_arn = role_arn
            self._diff.append(diff)

    def set_execution_role_arn(self, execution_role_arn):
        if execution_role_arn:
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'execution_role_arn',
                value=execution_role_arn,
                old_value=self.execution_role_arn
            )
            self.execution_role_arn = execution_role_arn
            self._diff.append(diff)


class EcsTaskDefinitionDiff(object):
    def __init__(self, container, field, value, old_value):
        self.container = container
        self.field = field
        self.value = value
        self.old_value = old_value

    def __repr__(self):
        if self.field == u'environment':
            return '\n'.join(self._get_environment_diffs(
                self.container,
                self.value,
                self.old_value,
            ))
        elif self.field == u'secrets':
            return '\n'.join(self._get_secrets_diffs(
                self.container,
                self.value,
                self.old_value,
            ))
        elif self.container:
            return u'Changed %s of container "%s" to: "%s" (was: "%s")' % (
                self.field,
                self.container,
                self.value,
                self.old_value
            )
        else:
            return u'Changed %s to: "%s" (was: "%s")' % (
                self.field,
                self.value,
                self.old_value
            )

    @staticmethod
    def _get_environment_diffs(container, env, old_env):
        msg = u'Changed environment "%s" of container "%s" to: "%s"'
        msg_removed = u'Removed environment "%s" of container "%s"'
        diffs = []
        for name, value in env.items():
            old_value = old_env.get(name)
            if value != old_value or value and not old_value:
                message = msg % (name, container, value)
                diffs.append(message)
        for old_name in old_env.keys():
            if old_name not in env.keys():
                message = msg_removed % (old_name, container)
                diffs.append(message)
        return diffs

    @staticmethod
    def _get_secrets_diffs(container, secrets, old_secrets):
        msg = u'Changed secret "%s" of container "%s" to: "%s"'
        msg_removed = u'Removed secret "%s" of container "%s"'
        diffs = []
        for name, value in secrets.items():
            old_value = old_secrets.get(name)
            if value != old_value or not old_value:
                message = msg % (name, container, value)
                diffs.append(message)
        for old_name in old_secrets.keys():
            if old_name not in secrets.keys():
                message = msg_removed % (old_name, container)
                diffs.append(message)
        return diffs


class EcsAction(object):
    def __init__(self, client, cluster_name, service_name):
        self._client = client
        self._cluster_name = cluster_name
        self._service_name = service_name

        try:
            if service_name:
                self._service = self.get_service()
        except IndexError:
            raise EcsConnectionError(
                u'An error occurred when calling the DescribeServices '
                u'operation: Service not found.'
            )
        except ClientError as e:
            raise EcsConnectionError(str(e))
        except NoCredentialsError:
            raise EcsConnectionError(
                u'Unable to locate credentials. Configure credentials '
                u'by running "aws configure".'
            )

    def get_service(self):
        services_definition = self._client.describe_services(
            cluster_name=self._cluster_name,
            service_name=self._service_name
        )
        return EcsService(
            cluster=self._cluster_name,
            service_definition=services_definition[u'services'][0]
        )

    def get_current_task_definition(self, service):
        return self.get_task_definition(service.task_definition)

    def get_task_definition(self, task_definition):
        task_definition_payload = self._client.describe_task_definition(
            task_definition_arn=task_definition
        )

        task_definition = EcsTaskDefinition(
            tags=task_definition_payload.get('tags', None),
            **task_definition_payload[u'taskDefinition']
        )
        return task_definition

    def update_task_definition(self, task_definition):
        response = self._client.register_task_definition(
            family=task_definition.family,
            containers=task_definition.containers,
            volumes=task_definition.volumes,
            role_arn=task_definition.role_arn,
            execution_role_arn=task_definition.execution_role_arn,
            tags=task_definition.tags,
            additional_properties=task_definition.additional_properties
        )
        new_task_definition = EcsTaskDefinition(**response[u'taskDefinition'])
        return new_task_definition

    def deregister_task_definition(self, task_definition):
        self._client.deregister_task_definition(task_definition.arn)

    def update_service(self, service, desired_count=None):
        response = self._client.update_service(
            cluster=service.cluster,
            service=service.name,
            desired_count=desired_count,
            task_definition=service.task_definition
        )
        return EcsService(self._cluster_name, response[u'service'])

    def is_deployed(self, service):
        if len(service[u'deployments']) != 1:
            return False
        running_tasks = self._client.list_tasks(
            cluster_name=service.cluster,
            service_name=service.name
        )
        if not running_tasks[u'taskArns']:
            return service.desired_count == 0
        running_count = self.get_running_tasks_count(
            service=service,
            task_arns=running_tasks[u'taskArns']
        )
        return service.desired_count == running_count

    def get_running_tasks_count(self, service, task_arns):
        running_count = 0
        tasks_details = self._client.describe_tasks(
            cluster_name=self._cluster_name,
            task_arns=task_arns
        )
        for task in tasks_details[u'tasks']:
            arn = task[u'taskDefinitionArn']
            status = task[u'lastStatus']
            if arn == service.task_definition and status == u'RUNNING':
                running_count += 1
        return running_count

    @property
    def client(self):
        return self._client

    @property
    def service(self):
        return self._service

    @property
    def cluster_name(self):
        return self._cluster_name

    @property
    def service_name(self):
        return self._service_name


class DeployAction(EcsAction):
    def deploy(self, task_definition):
        try:
            self._service.set_task_definition(task_definition)
            return self.update_service(self._service)
        except ClientError as e:
            raise EcsError(str(e))


class ScaleAction(EcsAction):
    def scale(self, desired_count):
        try:
            return self.update_service(self._service, desired_count)
        except ClientError as e:
            raise EcsError(str(e))


class RunAction(EcsAction):
    def __init__(self, client, cluster_name):
        super(RunAction, self).__init__(client, cluster_name, None)
        self._client = client
        self._cluster_name = cluster_name
        self.started_tasks = []

    def run(self, task_definition, count, started_by, launchtype, subnets,
            security_groups, public_ip, platform_version):
        try:
            result = self._client.run_task(
                cluster=self._cluster_name,
                task_definition=task_definition.family_revision,
                count=count,
                started_by=started_by,
                overrides=dict(containerOverrides=task_definition.get_overrides()),
                launchtype=launchtype,
                subnets=subnets,
                security_groups=security_groups,
                public_ip=public_ip,
                platform_version=platform_version,
            )
            self.started_tasks = result['tasks']
            return True
        except ClientError as e:
            raise EcsError(str(e))


class UpdateAction(EcsAction):
    def __init__(self, client):
        super(UpdateAction, self).__init__(client, None, None)


class DiffAction(EcsAction):
    def __init__(self, client):
        super(DiffAction, self).__init__(client, None, None)


class EcsError(Exception):
    pass


class EcsConnectionError(EcsError):
    pass


class UnknownContainerError(EcsError):
    pass


class TaskPlacementError(EcsError):
    pass


class UnknownTaskDefinitionError(EcsError):
    pass


class EcsTaskDefinitionCommandError(EcsError):
    pass
