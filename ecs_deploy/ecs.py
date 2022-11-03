from datetime import datetime
import json
import re
import copy
from collections import defaultdict
import logging
import click_log

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

logger = logging.getLogger(__name__)
click_log.basic_config(logger)


def read_env_file(container_name, file):
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
                 region=None, profile=None, session_token=None, assume_account=None, assume_role=None):

        if assume_account and assume_role:
            access_key_id, secret_access_key, session_token = self.assume_role(access_key_id, secret_access_key, region,
                                                                               profile, session_token, assume_account,
                                                                               assume_role)
            profile = None

        session = Session(aws_access_key_id=access_key_id,
                          aws_secret_access_key=secret_access_key,
                          aws_session_token=session_token,
                          region_name=region,
                          profile_name=profile)
        self.boto = session.client(u'ecs')
        self.events = session.client(u'events')

    @staticmethod
    def assume_role(access_key_id=None, secret_access_key=None, region=None, profile=None, session_token=None,
                    assume_account=None, assume_role=None):
        role_arn = 'arn:aws:iam::%s:role/%s' % (assume_account, assume_role)
        sts_session = Session(aws_access_key_id=access_key_id,
                              aws_secret_access_key=secret_access_key,
                              aws_session_token=session_token,
                              region_name=region,
                              profile_name=profile)
        sts = sts_session.client('sts')
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName='ecsDeploy',
        )
        access_key_id = response['Credentials']['AccessKeyId']
        secret_access_key = response['Credentials']['SecretAccessKey']
        session_token = response['Credentials']['SessionToken']
        return access_key_id, secret_access_key, session_token


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
                                 execution_role_arn, runtime_platform, tags,
                                 cpu, memory,
                                 additional_properties):
        if tags:
            additional_properties['tags'] = tags

        if cpu:
            additional_properties['cpu'] = cpu

        if memory:
            additional_properties['memory'] = memory

        if runtime_platform:
            additional_properties['runtimePlatform'] = runtime_platform

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


class EcsDeployment(dict):
    STATUS_ACTIVE = u'ACTIVE'
    STATUS_PRIMARY = u'PRIMARY'
    ROLLOUT_STATE_FAILED = u'FAILED'
    ROLLOUT_STATE_COMPLETED = u'COMPLETED'

    @property
    def is_primary(self):
        return self.get(u'status') == self.STATUS_PRIMARY

    @property
    def is_active(self):
        return self.get(u'status') == self.STATUS_ACTIVE

    @property
    def has_failed(self):
        return self.get(u'rolloutState') == self.ROLLOUT_STATE_FAILED

    @property
    def has_completed(self):
        return self.get(u'rolloutState') == self.ROLLOUT_STATE_COMPLETED

    @property
    def rollout_state_reason(self):
        return self.get(u'rolloutStateReason', '')

    @property
    def failed_tasks(self):
        return self.get(u'failedTasks', 0)


class EcsService(dict):
    def __init__(self, cluster, service_definition=None, **kwargs):
        self._cluster = cluster
        self._deployments = []
        for deployment in service_definition.get(u'deployments', []):
            self._deployments.append(EcsDeployment(deployment))
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
    def primary_deployment(self):
        for deployment in self._deployments:
            if deployment.is_primary:
                return deployment

    @property
    def active_deployment(self):
        for deployment in self._deployments:
            if deployment.is_active:
                return deployment
        return self.primary_deployment

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
                 status, taskDefinitionArn, runtimePlatform=None, cpu=None, memory=None, requiresAttributes=None,
                 taskRoleArn=None, executionRoleArn=None, compatibilities=None,
                 tags=None, registeredAt=None, deregisteredAt=None, registeredBy=None, **kwargs):

        self.containers = containerDefinitions
        self.new_containers = {}
        self.volumes = volumes
        self.family = family
        self.revision = revision
        self.status = status
        self.arn = taskDefinitionArn
        self.requires_attributes = requiresAttributes or {}
        self.role_arn = taskRoleArn or u''
        self.execution_role_arn = executionRoleArn or u''
        self.runtime_platform = runtimePlatform or {}
        self.cpu = cpu
        self.memory = memory
        self.tags = tags
        self.additional_properties = kwargs
        self._diff = []

        # the following parameters are returned from the ECS API, when
        # describing a task, but may not be included, when registering a new
        # task definition. Just storing them for now.
        self.compatibilities = compatibilities
        self.registered_at = registeredAt
        self.deregistered_at = deregisteredAt
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

        for container in containers_a:
            containers_a[container]['dockerLabels'] = containers_a[container].get('dockerLabels', {}).copy()

        for container in containers_b:
            containers_b[container]['dockerLabels'] = containers_b[container].get('dockerLabels', {}).copy()

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
            elif diff.field == 'dockerLabels':
                override['dockerLabels'] = self.get_overrides_docker_labels(diff.value)
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

    @staticmethod
    def get_overrides_docker_labels(dockerlabels):
        return dockerlabels.copy()

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

    def set_health_checks(self, health_checks_list):
        health_checks = defaultdict(dict)
        for health_check in health_checks_list:
            health_checks[health_check[0]]["command"] = ['CMD-SHELL', health_check[1]]
            health_checks[health_check[0]]["interval"] = health_check[2]
            health_checks[health_check[0]]["timeout"] = health_check[3]
            health_checks[health_check[0]]["retries"] = health_check[4]
            health_checks[health_check[0]]["startPeriod"] = health_check[5]

        self.validate_container_options(**health_checks)
        for container in self.containers:
            if container[u'name'] in health_checks:
                new_health_checks = health_checks[container[u'name']]
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'healthCheck',
                    value=new_health_checks,
                    old_value=container.get(u'healthCheck')
                )
                self._diff.append(diff)
                container[u'healthCheck'] = new_health_checks

    def set_runtime_platform(self, runtime_platform):
        if runtime_platform:
            new_runtime_platform = {}
            new_runtime_platform[u'cpuArchitecture'] = runtime_platform[0]
            new_runtime_platform[u'operatingSystemFamily'] = runtime_platform[1]
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'runtimePlatform',
                value=new_runtime_platform,
                old_value=self.runtime_platform
            )
            self.runtime_platform = new_runtime_platform
            self._diff.append(diff)

    def set_cpu(self, **cpu):
        self.validate_container_options(**cpu)
        for container in self.containers:
            if container[u'name'] in cpu:
                new_cpu = int(cpu[container[u'name']])
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'cpu',
                    value=new_cpu,
                    old_value=container.get(u'cpu')
                )

                self._diff.append(diff)
                container[u'cpu'] = new_cpu

    def set_task_cpu(self, task_cpu):
        if task_cpu:
            new_cpu = str(task_cpu)
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'cpu',
                value=new_cpu,
                old_value=self.cpu
            )
            self._diff.append(diff)
            self.cpu = new_cpu

    def set_task_memory(self, task_memory):
        if task_memory:
            new_memory = str(task_memory)
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'memory',
                value=new_memory,
                old_value=self.memory
            )
            self._diff.append(diff)
            self.memory = new_memory

    def set_memory(self, **memory):
        self.validate_container_options(**memory)
        for container in self.containers:
            if container[u'name'] in memory:
                new_memory = int(memory[container[u'name']])
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'memory',
                    value=new_memory,
                    old_value=container.get(u'memory')
                )
                self._diff.append(diff)
                container[u'memory'] = new_memory

    def set_memoryreservation(self, **memoryreservation):
        self.validate_container_options(**memoryreservation)
        for container in self.containers:
            if container[u'name'] in memoryreservation:
                new_memoryreservation = int(memoryreservation[container[u'name']])
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'memoryReservation',
                    value=new_memoryreservation,
                    old_value=container.get(u'memoryReservation')
                )
                self._diff.append(diff)
                container[u'memoryReservation'] = new_memoryreservation

    def set_privileged(self, **privileged):
        self.validate_container_options(**privileged)
        for container in self.containers:
            if container[u'name'] in privileged:
                new_privileged = bool(privileged[container[u'name']])
                old_privileged = container.get(u'privileged')
                if not new_privileged == old_privileged:
                    diff = EcsTaskDefinitionDiff(
                        container=container[u'name'],
                        field=u'privileged',
                        value=new_privileged,
                        old_value=old_privileged
                    )
                    self._diff.append(diff)
                    container[u'privileged'] = new_privileged

    def set_essential(self, **essential):
        self.validate_container_options(**essential)
        for container in self.containers:
            if container[u'name'] in essential:
                new_essential = bool(essential[container[u'name']])
                old_essential = container.get(u'essential')
                if not new_essential == old_essential:
                    diff = EcsTaskDefinitionDiff(
                        container=container[u'name'],
                        field=u'essential',
                        value=new_essential,
                        old_value=old_essential
                    )
                    self._diff.append(diff)
                    container[u'essential'] = new_essential

    def set_log_configurations(self, log_configurations_list):
        log_configurations = defaultdict(dict)
        for log_configuration in log_configurations_list:
            log_configurations[log_configuration[0]]["logDriver"] = log_configuration[1]
            log_configurations[log_configuration[0]].setdefault("options", {})
            log_configurations[log_configuration[0]]["options"][log_configuration[2]] = log_configuration[3]
            log_configurations[log_configuration[0]]["secretOptions"] = []

        self.validate_container_options(**log_configurations)
        for container in self.containers:
            if container[u'name'] in log_configurations:
                new_log_configurations = log_configurations[container[u'name']]
                diff = EcsTaskDefinitionDiff(
                    container=container[u'name'],
                    field=u'logConfiguration',
                    value=new_log_configurations,
                    old_value=container.get(u'logConfiguration')
                )
                self._diff.append(diff)
                container[u'logConfiguration'] = new_log_configurations

    def set_environment(self, environment_list, exclusive=False, env_file=((None, None),)):
        environment = defaultdict(dict)
        if None not in env_file[0]:
            for env in env_file:
                l = read_env_file(env[0], env[1])
                environment_list = l + environment_list
        for env in environment_list:
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

    def set_docker_labels(self, dockerlabel_list, exclusive=False):
        dockerlabels = defaultdict(dict)
        for label in dockerlabel_list:
            dockerlabels[label[0]][label[1]] = label[2]
        self.validate_container_options(**dockerlabels)
        for container in self.containers:
            if container[u'name'] in dockerlabels:
                self.apply_docker_labels(
                    container=container,
                    new_dockerlabels=dockerlabels[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_docker_labels(
                    container=container,
                    new_dockerlabels={},
                    exclusive=exclusive,
                )

    def apply_docker_labels(self, container, new_dockerlabels, exclusive=False):
        old_dockerlabels = container.get('dockerLabels', {})

        if exclusive is True:
            merged = new_dockerlabels
        else:
            merged = old_dockerlabels.copy()
            merged.update(new_dockerlabels)

        if old_dockerlabels == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'dockerLabels',
            value=merged,
            old_value=old_dockerlabels
        )
        self._diff.append(diff)

        container[u'dockerLabels'] = merged.copy()
    def set_s3_env_file(self, s3_env_files, exclusive=False):
        # environmentFiles in task definition https://docs.aws.amazon.com/AmazonECS/latest/developerguide/taskdef-envfiles.html
        s3_files_by_container = defaultdict(list)
        if s3_env_files:
            multiple_s3_env_files = any(isinstance(i, tuple) for i in s3_env_files)
            if not multiple_s3_env_files:
                s3_files_by_container[s3_env_files[0]] = {s3_env_files[1]}
            if multiple_s3_env_files:
                for s3_file in s3_env_files:
                    if s3_files_by_container[s3_file[0]]:
                        s3_files_by_container[s3_file[0]].add(s3_file[1])
                        break
                    s3_files_by_container[s3_file[0]] = {s3_file[1]}

        for container in self.containers:
            if container[u'name'] in s3_files_by_container:
                self.apply_s3_env_file(
                    container=container,
                    new_s3_env_file=s3_files_by_container[container[u'name']],
                    exclusive=exclusive
                )
            elif exclusive is True:
                self.apply_s3_env_file(
                    container=container,
                    new_s3_env_file={},
                    exclusive=exclusive
                )

    def apply_s3_env_file(self, container, new_s3_env_file, exclusive=False):
        s3_env_file = container.get('environmentFiles', {})
        old_s3_env_file = {env_file['value'] for env_file in s3_env_file}

        if exclusive is True:
            merged = new_s3_env_file
        else:
            merged = old_s3_env_file.copy()
            merged.update(new_s3_env_file)

        if old_s3_env_file == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'environmentFiles',
            value=merged,
            old_value=old_s3_env_file
        )
        self._diff.append(diff)
        container[u'environmentFiles'] = [
            {"value": e, "type": "s3"} for e in merged
        ]

    def set_secrets(self, secrets_list, exclusive=False, env_file=((None, None),)):
        secrets = defaultdict(dict)

        if None not in env_file[0]:
            for secret in env_file:
                l = read_env_file(secret[0], secret[1])
                secrets_list = l + secrets_list

        for secret in secrets_list:
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

    def set_system_controls(self, system_controls_list, exclusive=False):
        system_controls = defaultdict(list)
        for system_control in system_controls_list:

            mapping = {}
            mapping["namespace"] = system_control[1]
            mapping["value"] = system_control[2]
            system_controls[system_control[0]].append(mapping)

        self.validate_container_options(**system_controls)
        for container in self.containers:
            if container[u'name'] in system_controls:
                self.apply_container_system_controls(
                    container=container,
                    new_system_controls=system_controls[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_system_controls(
                    container=container,
                    new_system_controls={},
                    exclusive=exclusive,
                )

    def apply_container_system_controls(self, container, new_system_controls, exclusive=False):
        system_controls = container.get('systemControls', [])
        old_system_controls = [ {name: value for name, value in system_control.items()} for system_control in system_controls]

        if exclusive is True:
            merged = new_system_controls if new_system_controls else []
        else:
            merged = copy.deepcopy(old_system_controls)
            old_system_control_namespaces = [system_control["namespace"] for system_control in merged]
            new_system_control_namespaces = [system_control["namespace"] for system_control in new_system_controls]
            new = set(new_system_control_namespaces) - set(old_system_control_namespaces)
            new_merged = list()
            # update
            for system_control in merged:
                for new_system_control in new_system_controls:
                    if system_control["namespace"] == new_system_control["namespace"]:
                        system_control.update(new_system_control)
            # new
            for name in new:
                for new_system_control in new_system_controls:
                    if name == new_system_control["namespace"]:
                        new_merged.append(new_system_control)

            merged.extend(new_merged)

        if old_system_controls == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'systemControls',
            value=merged,
            old_value=old_system_controls
        )
        self._diff.append(diff)

        container[u'systemControls'] = [
            {name: value for name,value in e.items()} for e in merged
        ]

    def set_ulimits(self, ulimits_list, exclusive=False):
        ulimits = defaultdict(list)
        for ulimit in ulimits_list:

            mapping = {}
            mapping["name"] = ulimit[1]
            mapping["softLimit"] = int(ulimit[2])
            mapping["hardLimit"] = int(ulimit[3])
            ulimits[ulimit[0]].append(mapping)

        self.validate_container_options(**ulimits)
        for container in self.containers:
            if container[u'name'] in ulimits:
                self.apply_container_ulimits(
                    container=container,
                    new_ulimits=ulimits[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_ulimits(
                    container=container,
                    new_ulimits={},
                    exclusive=exclusive,
                )

    def apply_container_ulimits(self, container, new_ulimits, exclusive=False):
        ulimits = container.get('ulimits', [])
        old_ulimits = [ {name: value for name, value in ulimit.items()} for ulimit in ulimits]

        if exclusive is True:
            merged = new_ulimits if new_ulimits else []
        else:
            merged = copy.deepcopy(old_ulimits)
            old_ulimit_names = [ulimit["name"] for ulimit in merged]
            new_ulimit_names = [ulimit["name"] for ulimit in new_ulimits]
            new = set(new_ulimit_names) - set(old_ulimit_names)
            new_merged = list()
            # update
            for ulimit in merged:
                for new_ulimit in new_ulimits:
                    if ulimit["name"] == new_ulimit["name"]:
                        ulimit.update(new_ulimit)
            # new
            for name in new:
                for new_ulimit in new_ulimits:
                    if name == new_ulimit["name"]:
                        new_merged.append(new_ulimit)

            merged.extend(new_merged)

        if old_ulimits == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'ulimits',
            value=merged,
            old_value=old_ulimits
        )
        self._diff.append(diff)

        container[u'ulimits'] = [
            {name: value for name,value in e.items()} for e in merged
        ]

    def set_port_mappings(self, port_mappings_list, exclusive=False):
        port_mappings = defaultdict(list)

        for port_mapping in port_mappings_list:
            mapping = {}
            mapping["containerPort"] = int(port_mapping[1])
            mapping["hostPort"] = int(port_mapping[2])
            mapping["protocol"] = "tcp"
            port_mappings[port_mapping[0]].append(mapping)

        self.validate_container_options(**port_mappings)
        for container in self.containers:
            if container[u'name'] in port_mappings:
                self.apply_container_port_mappings(
                    container=container,
                    new_port_mappings=port_mappings[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_port_mappings(
                    container=container,
                    new_port_mappings={},
                    exclusive=exclusive,
                )

    def apply_container_port_mappings(self, container, new_port_mappings, exclusive=False):
        port_mappings = container.get('portMappings', [])
        old_port_mappings = [ {name: value for name, value in port_mapping.items()} for port_mapping in port_mappings]

        if exclusive is True:
            merged = new_port_mappings if new_port_mappings else []
        else:
            merged = copy.deepcopy(old_port_mappings)
            old_container_ports = [port_mapping["containerPort"] for port_mapping in merged]
            new_container_ports = [port_mapping["containerPort"] for port_mapping in new_port_mappings]
            new = set(new_container_ports) - set(old_container_ports)
            new_merged = list()
            # update
            for port_mapping in merged:
                for new_port_mapping in new_port_mappings:
                    if port_mapping["containerPort"] == new_port_mapping["containerPort"]:
                        port_mapping.update(new_port_mapping)
            # new
            for port in new:
                for new_port_mapping in new_port_mappings:
                    if port == new_port_mapping["containerPort"]:
                        new_merged.append(new_port_mapping)

            merged.extend(new_merged)
        if old_port_mappings == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'portMappings',
            value=merged,
            old_value=old_port_mappings
        )
        self._diff.append(diff)

        container[u'portMappings'] = [
            {name: value for name,value in e.items()} for e in merged
        ]

    def set_mount_points(self, mount_points_list, exclusive=False):
        mount_points = defaultdict(list)
        for mount_point in mount_points_list:
            mapping = {}
            mapping["sourceVolume"] = mount_point[1]
            mapping["containerPath"] = mount_point[2]
            mapping["readOnly"] = False
            mount_points[mount_point[0]].append(mapping)

        self.validate_container_options(**mount_points)
        for container in self.containers:
            if container[u'name'] in mount_points:
                self.apply_container_mount_points(
                    container=container,
                    new_mount_points=mount_points[container[u'name']],
                    exclusive=exclusive,
                )
            elif exclusive is True:
                self.apply_container_mount_points(
                    container=container,
                    new_mount_points={},
                    exclusive=exclusive,
                )

    def apply_container_mount_points(self, container, new_mount_points, exclusive=False):
        mount_points = container.get('mountPoints', [])
        old_mount_points = [ {name: value for name, value in mount_point.items()} for mount_point in mount_points]

        if exclusive is True:
            merged = new_mount_points if new_mount_points else []
        else:
            merged = copy.deepcopy(old_mount_points)
            old_source_volumes = [mount_point["sourceVolume"] for mount_point in merged]
            new_source_volumes = [mount_point["sourceVolume"] for mount_point in new_mount_points]
            new = set(new_source_volumes) - set(old_source_volumes)
            new_merged = list()
            # update
            for mount_point in merged:
                for new_mount_point in new_mount_points:
                    if mount_point["sourceVolume"] == new_mount_point["sourceVolume"]:
                        mount_point.update(new_mount_point)
            # new
            for volume in new:
                for new_mount_point in new_mount_points:
                    if volume == new_mount_point["sourceVolume"]:
                        new_merged.append(new_mount_point)

            merged.extend(new_merged)

        if old_mount_points == merged:
            return

        diff = EcsTaskDefinitionDiff(
            container=container[u'name'],
            field=u'mountPoints',
            value=merged,
            old_value=old_mount_points
        )
        self._diff.append(diff)

        container[u'mountPoints'] = [
            {name: value for name,value in e.items()} for e in merged
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

    def set_volumes(self, volumes_list):
        volumes = []

        for volume in volumes_list:
            mapping = defaultdict(dict)
            mapping["name"] = volume[0]
            mapping["host"]["sourcePath"] = volume[1]
            volumes.append(mapping)

        if volumes:
            diff = EcsTaskDefinitionDiff(
                container=None,
                field=u'volumes',
                value=volumes,
                old_value=self.volumes
            )
            self.volumes = volumes
            self._diff.append(diff)

    def add_containers(self, containers_list):
        """Add new containers.

        For every new container specified a placeholder container is added to the task defintion:
          * 'name' is the string givenin the parameter list.
          * 'image' is just 'PLACEHOLDER'.

        The idea is to actually set sensible values for this container when deploying.
        """

        if containers_list:
            containers_tmp = list(self.containers)
            for container in set(containers_list):
                if container in self.container_names:
                    logger.warning("Cannot add container '{container}', already in the task definition.".format(container=container))
                    continue
                mapping = {}
                mapping["name"] = container
                mapping["image"] = "PLACEHOLDER"
                mapping["cpu"] = 0
                mapping["memoryReservation"] = 128
                mapping["essential"] = True
                self.containers.append(mapping)

            if not self.containers == containers_tmp:
                diff = EcsTaskDefinitionDiff(
                    container=None,
                    field=u'containers',
                    value=self.containers,
                    old_value=containers_tmp
                )
                self._diff.append(diff)

    def remove_containers(self, containers_list):
        """Remove containers.
        """
        if containers_list:
            # Remove possible duplicates.
            containers_ = set(containers_list)

            containers_tmp = list(self.containers)
            containers = list()
            for container in self.containers:
                if container["name"] not in containers_:
                    # Leave container.
                    containers.append(container)

            containers_not_found = list(containers_ - set(self.container_names))
            # Remaining containers could not be found.
            for container in containers_not_found:
                logger.warning("Cannot remove container '{container}', not in the task definition.".format(container=container))

            if containers:
                self.containers = containers
            else:
                logger.warning("No container left after removal. Using original containers, not removing '{containers_}'.".format(container=container))

            if not self.containers == containers_tmp:
                diff = EcsTaskDefinitionDiff(
                    container=None,
                    field=u'containers',
                    value=self.containers,
                    old_value=containers_tmp
                )
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
        elif self.field == u'dockerLabels':
            return '\n'.join(self._get_docker_label_diffs(
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
    def _get_docker_label_diffs(container, dockerlabels, old_dockerlabels):
        msg = u'Changed dockerLabel "%s" of container "%s" to: "%s"'
        msg_removed = u'Removed dockerLabel "%s" of container "%s"'
        diffs = []
        for name, value in dockerlabels.items():
            old_value = old_dockerlabels.get(name)
            if value != old_value or value and not old_value:
                message = msg % (name, container, value)
                diffs.append(message)
        for old_name in old_dockerlabels.keys():
            if old_name not in dockerlabels.keys():
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
    FAILED_TASKS = 0

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
            runtime_platform=task_definition.runtime_platform,
            tags=task_definition.tags,
            additional_properties=task_definition.additional_properties,
            cpu=task_definition.cpu,
            memory=task_definition.memory
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
        if service.primary_deployment.has_failed:
            raise EcsDeploymentError(u'Deployment Failed! ' + service.primary_deployment.rollout_state_reason)
        if service.primary_deployment.failed_tasks > 0 and service.primary_deployment.failed_tasks != self.FAILED_TASKS:
            logger.warning('{} tasks failed to start'.format(service.primary_deployment.failed_tasks))
            self.FAILED_TASKS += 1

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


class EcsDeploymentError(EcsError):
    pass
