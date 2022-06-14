from copy import deepcopy
from datetime import datetime, timedelta

import pytest
import tempfile
import os
import logging
from boto3.session import Session
from botocore.exceptions import ClientError, NoCredentialsError
from dateutil.tz import tzlocal
from unittest.mock import patch

from ecs_deploy.ecs import EcsService, EcsTaskDefinition, \
    UnknownContainerError, EcsTaskDefinitionDiff, EcsClient, \
    EcsAction, EcsConnectionError, DeployAction, ScaleAction, RunAction, \
    EcsTaskDefinitionCommandError, UnknownTaskDefinitionError, LAUNCH_TYPE_EC2, read_env_file, EcsDeployment, \
    EcsDeploymentError

CLUSTER_NAME = 'test-cluster'
CLUSTER_ARN = 'arn:aws:ecs:eu-central-1:123456789012:cluster/%s' % CLUSTER_NAME
SERVICE_NAME = 'test-service'
SERVICE_ARN = 'ecs-svc/12345678901234567890'
DESIRED_COUNT = 2
TASK_DEFINITION_FAMILY_1 = 'test-task'
TASK_DEFINITION_REVISION_1 = 1
TASK_DEFINITION_ROLE_ARN_1 = 'arn:test:role:1'
TASK_DEFINITION_ARN_1 = 'arn:aws:ecs:eu-central-1:123456789012:task-definition/{}:{}'.format(TASK_DEFINITION_FAMILY_1,
                                                                                          TASK_DEFINITION_REVISION_1)
TASK_DEFINITION_RUNTIME_PLATFORM_1 = {'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'}
TASK_DEFINITION_VOLUMES_1 = []
TASK_DEFINITION_CONTAINERS_1 = [
    {'name': 'webserver', 'image': 'webserver:123', 'command': 'run',
     'environment': ({"name": "foo", "value": "bar"}, {"name": "lorem", "value": "ipsum"}, {"name": "empty", "value": ""}),
     'environmentFiles': [{'value': 'arn:aws:s3:::myS3bucket/myApp/.env', 'type': 's3'}, {'value': 'arn:aws:s3:::coolBuckets/dev/.env', 'type': 's3'}],
     'secrets': ({"name": "baz", "valueFrom": "qux"}, {"name": "dolor", "valueFrom": "sit"}),
     'dockerLabels': {"foo": "bar", "lorem": "ipsum", "empty": ""},
     'logConfiguration': {},
     'ulimits': [{'name': 'memlock', 'softLimit': 256, 'hardLimit': 256}],
     'systemControls': [{'namespace': 'net.core.somaxconn', 'value': '511'}],
     'portMappings': [{'containerPort': 8080, 'hostPort': 8080}],
     'mountPoints': [{'sourceVolume': 'volume', 'containerPath': '/container/path', 'readOnly': False}]},
    {'name': 'application', 'image': 'application:123', 'command': 'run', 'environment': (),
     'logConfiguration': {}, 'dockerLabels': {},
     'ulimits': [{'name': 'memlock', 'softLimit': 256, 'hardLimit': 256}],
     'systemControls': [{'namespace': 'net.core.somaxconn', 'value': '511'}],
     'portMappings': [{'containerPort': 8080, 'hostPort': 8080}],
     'mountPoints': [{'sourceVolume': 'volume', 'containerPath': '/container/path', 'readOnly': False}]}
]

TASK_DEFINITION_FAMILY_2 = 'test-task'
TASK_DEFINITION_REVISION_2 = 2
TASK_DEFINITION_ARN_2 = 'arn:aws:ecs:eu-central-1:123456789012:task-definition/{}:{}'.format(TASK_DEFINITION_FAMILY_2,
                                                                                          TASK_DEFINITION_REVISION_2)
TASK_DEFINITION_VOLUMES_2 = []
TASK_DEFINITION_CONTAINERS_2 = [
    {'name': 'webserver', 'image': 'webserver:123', 'command': 'run',
     'environment': ({"name": "foo", "value": "bar"}, {"name": "lorem", "value": "ipsum"}, {"name": "empty", "value": ""}),
     'environmentFiles': [{'value': 'arn:aws:s3:::myS3bucket/myApp/.env', 'type': 's3'}, {'value': 'arn:aws:s3:::coolBuckets/dev/.env', 'type': 's3'}],
     'secrets': ({"name": "baz", "valueFrom": "qux"}, {"name": "dolor", "valueFrom": "sit"}),
     'dockerLabels': {"foo": "bar", "lorem": "ipsum", "empty": ""},
     'logConfiguration': {},
     'ulimits': [{'name': 'memlock', 'softLimit': 256, 'hardLimit': 256}],
     'systemControls': [{'namespace': 'net.core.somaxconn', 'value': '511'}],
     'portMappings': [{'containerPort': 8080, 'hostPort': 8080}],
     'mountPoints': [{'sourceVolume': 'volume', 'containerPath': '/container/path', 'readOnly': False}]},
    {'name': 'application', 'image': 'application:123', 'command': 'run', 'environment': (),
     'logConfiguration': {}, 'dockerLabels': {},
     'ulimits': [{'name': 'memlock', 'softLimit': 256, 'hardLimit': 256}],
     'systemControls': [{'namespace': 'net.core.somaxconn', 'value': '511'}],
     'portMappings': [{'containerPort': 8080, 'hostPort': 8080}],
     'mountPoints': [{'sourceVolume': 'volume', 'containerPath': '/container/path', 'readOnly': False}]},
    
]

TASK_DEFINITION_REVISION_3 = 3
TASK_DEFINITION_ARN_3 = 'arn:aws:ecs:eu-central-1:123456789012:task-definition/{}:{}'.format(TASK_DEFINITION_FAMILY_1,
                                                                                          TASK_DEFINITION_REVISION_3)
TASK_DEFINITION_VOLUMES_3 = []
TASK_DEFINITION_CONTAINERS_3 = [
    {'name': 'webserver', 'image': 'webserver:456', 'command': 'execute',
     'environment': ({"name": "foo", "value": "foobar"}, {"name": "newvar", "value": "new value"}),
     'secrets': ({"name": "baz", "valueFrom": "foobaz"}, {"name": "dolor", "valueFrom": "loremdolor"}),
     'dockerLabels': {"foo": "foobar", "newlabel": "new value"}},
    {'name': 'application', 'image': 'application:123', 'command': 'run', 'environment': ()}
]
TASK_DEFINITION_ROLE_ARN_3 = 'arn:test:another-role:1'

PAYLOAD_TASK_DEFINITION_1 = {
    'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    'runtimePlatform': deepcopy(TASK_DEFINITION_RUNTIME_PLATFORM_1),
    'family': TASK_DEFINITION_FAMILY_1,
    'revision': TASK_DEFINITION_REVISION_1,
    'taskRoleArn': TASK_DEFINITION_ROLE_ARN_1,
    'executionRoleArn': TASK_DEFINITION_ROLE_ARN_1,
    'volumes': deepcopy(TASK_DEFINITION_VOLUMES_1),
    'containerDefinitions': deepcopy(TASK_DEFINITION_CONTAINERS_1),
    'status': 'active',
    'requiresAttributes': {},
    'networkMode': 'host',
    'placementConstraints': {},
    'registeredBy': 'foobar',
    'registeredAt': '2021-01-20T14:33:44Z',
    'deregisteredAt': '2021-01-20T14:33:44Z',
    'unknownProperty': 'lorem-ipsum',
    'compatibilities': ['EC2'],
}

PAYLOAD_TASK_DEFINITION_2 = {
    'taskDefinitionArn': TASK_DEFINITION_ARN_2,
    'family': TASK_DEFINITION_FAMILY_2,
    'revision': TASK_DEFINITION_REVISION_2,
    'volumes': deepcopy(TASK_DEFINITION_VOLUMES_2),
    'containerDefinitions': deepcopy(TASK_DEFINITION_CONTAINERS_2),
    'status': 'active',
    'unknownProperty': 'lorem-ipsum',
    'compatibilities': ['EC2'],
}

PAYLOAD_TASK_DEFINITION_3 = {
    'taskDefinitionArn': TASK_DEFINITION_ARN_3,
    'family': TASK_DEFINITION_FAMILY_1,
    'revision': TASK_DEFINITION_REVISION_3,
    'taskRoleArn': TASK_DEFINITION_ROLE_ARN_3,
    'executionRoleArn': TASK_DEFINITION_ROLE_ARN_3,
    'volumes': deepcopy(TASK_DEFINITION_VOLUMES_3),
    'containerDefinitions': deepcopy(TASK_DEFINITION_CONTAINERS_3),
    'status': 'active',
    'requiresAttributes': {},
    'networkMode': 'host',
    'placementConstraints': {},
    'unknownProperty': 'lorem-ipsum',
    'compatibilities': ['EC2'],
}

TASK_ARN_1 = 'arn:aws:ecs:eu-central-1:123456789012:task/12345678-1234-1234-1234-123456789011'
TASK_ARN_2 = 'arn:aws:ecs:eu-central-1:123456789012:task/12345678-1234-1234-1234-123456789012'

PAYLOAD_TASK_1 = {
    'taskArn': TASK_ARN_1,
    'clusterArn': CLUSTER_ARN,
    'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    'containerInstanceArn': 'arn:aws:ecs:eu-central-1:123456789012:container-instance/12345678-123456-123456-123456',
    'overrides': {'containerOverrides': []},
    'lastStatus': 'RUNNING',
    'desiredStatus': 'RUNNING',
    'containers': TASK_DEFINITION_CONTAINERS_1,
    'startedBy': SERVICE_ARN
}

PAYLOAD_TASK_2 = {
    'taskArn': TASK_ARN_2,
    'clusterArn': CLUSTER_ARN,
    'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    'containerInstanceArn': 'arn:aws:ecs:eu-central-1:123456789012:container-instance/12345678-123456-123456-123456',
    'overrides': {'containerOverrides': []},
    'lastStatus': 'RUNNING',
    'desiredStatus': 'RUNNING',
    'containers': TASK_DEFINITION_CONTAINERS_1,
    'startedBy': SERVICE_ARN
}

PAYLOAD_DEPLOYMENTS = [
    {
        'status': 'PRIMARY',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'COMPLETED',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 completed.',
        'failedTasks': 0,
    }
]

PAYLOAD_DEPLOYMENTS_IN_PROGRESS = [
    {
        'status': 'PRIMARY',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'IN_PROGRESS',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 in progress.',
        'failedTasks': 0,
    },
    {
        'status': 'ACTIVE',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'COMPLETED',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 completed.',
        'failedTasks': 0,
    }
]

PAYLOAD_DEPLOYMENTS_IN_PROGRESS_FAILED_TASKS = [
    {
        'status': 'PRIMARY',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'IN_PROGRESS',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 in progress.',
        'failedTasks': 3,
    },
    {
        'status': 'ACTIVE',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'COMPLETED',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 completed.',
        'failedTasks': 0,
    }
]

PAYLOAD_DEPLOYMENTS_FAILED = [
    {
        'status': 'PRIMARY',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'FAILED',
        'rolloutStateReason': 'ECS deployment circuit breaker: tasks failed to start.',
        'failedTasks': 10,
    },
    {
        'status': 'ACTIVE',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'COMPLETED',
        'rolloutStateReason': 'ECS deployment ecs-svc/5169280574093855189 completed.',
        'failedTasks': 0,
    }
]


PAYLOAD_DEPLOYMENTS_FAILED_ROLLBACK = [
    {
        'status': 'PRIMARY',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'IN_PROGRESS',
        'rolloutStateReason': 'ECS deployment circuit breaker: rolling back to deploymentId ecs-svc/123456789012345',
    },
    {
        'status': 'ACTIVE',
        'pendingCount': 0,
        'desiredCount': DESIRED_COUNT,
        'runningCount': DESIRED_COUNT,
        'taskDefinition': TASK_DEFINITION_ARN_1,
        'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        'id': 'ecs-svc/0000000000000000002',
        'rolloutState': 'FAILED',
        'rolloutStateReason': 'ECS deployment circuit breaker: tasks failed to start.',
    }
]

PAYLOAD_EVENTS = [
    {
        'id': 'error',
        'createdAt': datetime.now(tz=tzlocal()),
        'message': 'Service was unable to Lorem Ipsum'
    },
    {
        'id': 'older_error',
        'createdAt': datetime(2016, 3, 11, 12, 0, 10, 000000, tzinfo=tzlocal()),
        'message': 'Service was unable to Lorem Ipsum'
    }
]

PAYLOAD_SERVICE = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS,
    'events': []
}

PAYLOAD_SERVICE_WITH_ERRORS = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS,
    'events': PAYLOAD_EVENTS
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENTS = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': [],
    'events': []
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_IN_PROGRESS = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS_IN_PROGRESS,
    'events': []
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_IN_PROGRESS_FAILED_TASKS = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS_IN_PROGRESS_FAILED_TASKS,
    'events': []
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_FAILED_NO_ROLLBACK = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS_FAILED,
    'events': []
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_FAILED_WITH_ROLLBACK = {
    'serviceName': SERVICE_NAME,
    'desiredCount': DESIRED_COUNT,
    'taskDefinition': TASK_DEFINITION_ARN_1,
    'deployments': PAYLOAD_DEPLOYMENTS_FAILED_ROLLBACK,
    'events': []
}

RESPONSE_SERVICE = {
    "service": PAYLOAD_SERVICE
}

RESPONSE_SERVICE_WITH_ERRORS = {
    "service": PAYLOAD_SERVICE_WITH_ERRORS
}

RESPONSE_DESCRIBE_SERVICES = {
    "services": [PAYLOAD_SERVICE]
}

RESPONSE_TASK_DEFINITION = {
    "taskDefinition": PAYLOAD_TASK_DEFINITION_1
}

RESPONSE_TASK_DEFINITION_2 = {
    "taskDefinition": PAYLOAD_TASK_DEFINITION_2
}

RESPONSE_TASK_DEFINITION_3 = {
    "taskDefinition": PAYLOAD_TASK_DEFINITION_3
}

RESPONSE_TASK_DEFINITIONS = {
    TASK_DEFINITION_ARN_1: RESPONSE_TASK_DEFINITION,
    TASK_DEFINITION_ARN_2: RESPONSE_TASK_DEFINITION_2,
    TASK_DEFINITION_ARN_3: RESPONSE_TASK_DEFINITION_3,
    'test-task:1': RESPONSE_TASK_DEFINITION,
    'test-task:2': RESPONSE_TASK_DEFINITION_2,
    'test-task:3': RESPONSE_TASK_DEFINITION_3,
    'test-task': RESPONSE_TASK_DEFINITION_2,
}

RESPONSE_LIST_TASKS_2 = {
    "taskArns": [TASK_ARN_1, TASK_ARN_2]
}

RESPONSE_LIST_TASKS_1 = {
    "taskArns": [TASK_ARN_1]
}

RESPONSE_LIST_TASKS_0 = {
    "taskArns": []
}

RESPONSE_DESCRIBE_TASKS = {
    "tasks": [PAYLOAD_TASK_1, PAYLOAD_TASK_2]
}


@pytest.fixture()
def task_definition():
    return EcsTaskDefinition(**deepcopy(PAYLOAD_TASK_DEFINITION_1))


@pytest.fixture
def task_definition_revision_2():
    return EcsTaskDefinition(**deepcopy(PAYLOAD_TASK_DEFINITION_2))


@pytest.fixture
def service():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE))


@pytest.fixture
def service_with_errors():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITH_ERRORS))


@pytest.fixture
def service_without_deployments():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITHOUT_DEPLOYMENTS))


@pytest.fixture
def service_with_failed_deployment():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_FAILED_NO_ROLLBACK))


@pytest.fixture
def service_with_failed_tasks():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_IN_PROGRESS_FAILED_TASKS))


def test_service_init(service):
    assert isinstance(service, dict)
    assert service.cluster == CLUSTER_NAME
    assert service['desiredCount'] == DESIRED_COUNT
    assert service['taskDefinition'] == TASK_DEFINITION_ARN_1


def test_service_set_task_definition(service, task_definition):
    assert service.task_definition == TASK_DEFINITION_ARN_1
    service.set_task_definition(task_definition)
    assert service.task_definition == task_definition.arn


def test_service_name(service):
    assert service.name == SERVICE_NAME


def test_service_deployment_created_at(service):
    assert service.deployment_created_at == datetime(2016, 3, 11, 12, 00, 00, 000000, tzinfo=tzlocal())


def test_service_deployment_updated_at(service):
    assert service.deployment_updated_at == datetime(2016, 3, 11, 12, 5, 00, 000000, tzinfo=tzlocal())


def test_service_deployment_created_at_without_deployments(service_without_deployments):
    now = datetime.now()
    assert service_without_deployments.deployment_created_at >= now
    assert service_without_deployments.deployment_created_at <= datetime.now()


def test_service_deployment_updated_at_without_deployments(service_without_deployments):
    now = datetime.now()
    assert service_without_deployments.deployment_updated_at >= now
    assert service_without_deployments.deployment_updated_at <= datetime.now()


def test_service_errors(service_with_errors):
    assert len(service_with_errors.errors) == 1


def test_service_older_errors(service_with_errors):
    assert len(service_with_errors.older_errors) == 1


def test_task_family(task_definition):
    assert task_definition.family == TASK_DEFINITION_FAMILY_1


def test_task_containers(task_definition):
    assert task_definition.containers == TASK_DEFINITION_CONTAINERS_2


def test_task_container_names(task_definition):
    assert 'webserver' in task_definition.container_names
    assert 'application' in task_definition.container_names
    assert 'foobar' not in task_definition.container_names


def test_task_volumes(task_definition):
    assert task_definition.volumes == TASK_DEFINITION_VOLUMES_2


def test_task_revision(task_definition):
    assert task_definition.revision == TASK_DEFINITION_REVISION_1


def test_task_no_diff(task_definition):
    assert task_definition.diff == []


def test_task_image_diff(task_definition):
    task_definition.set_images('foobar')
    assert len(task_definition.diff) == 2

    for diff in task_definition.diff:
        assert isinstance(diff, EcsTaskDefinitionDiff)


def test_task_set_tag(task_definition):
    task_definition.set_images('foobar')
    for container in task_definition.containers:
        assert container['image'].endswith(':foobar')


def test_task_set_image(task_definition):
    task_definition.set_images(webserver='new-image:123', application='app-image:latest')
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['image'] == 'new-image:123'
        if container['name'] == 'application':
            assert container['image'] == 'app-image:latest'

def test_task_set_cpu(task_definition):
    task_definition.set_cpu(webserver=10, application=0)
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['cpu'] == 10
        if container['name'] == 'application':
            assert container['cpu'] == 0

def test_task_set_memory(task_definition):
    task_definition.set_memory(webserver=256, application=128)
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['memory'] == 256
        if container['name'] == 'application':
            assert container['memory'] == 128

def test_task_set_memoryreservation(task_definition):
    task_definition.set_memoryreservation(webserver=128, application=64)
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['memoryReservation'] == 128
        if container['name'] == 'application':
            assert container['memoryReservation'] == 64

def test_task_set_privileged(task_definition):
    task_definition.set_privileged(webserver=False, application=True)
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['privileged'] == False
        if container['name'] == 'application':
            assert container['privileged'] == True

def test_task_set_log_configurations(task_definition):
    assert len(task_definition.containers[0]['logConfiguration']) == 0

    task_definition.set_log_configurations((('webserver', 'awslogs', 'awslogs-group', 'service_logs'), ('webserver', 'awslogs', 'awslogs-region', 'eu-central-1')))

    assert len(task_definition.containers[0]['logConfiguration']) > 0

    assert('logDriver' in task_definition.containers[0]['logConfiguration'])
    assert 'awslogs' == task_definition.containers[0]['logConfiguration']['logDriver']
    assert 'options' in task_definition.containers[0]['logConfiguration']
    assert 'awslogs-group' in task_definition.containers[0]['logConfiguration']['options']
    assert 'service_logs' == task_definition.containers[0]['logConfiguration']['options']['awslogs-group']
    assert 'awslogs-region' in task_definition.containers[0]['logConfiguration']['options']
    assert 'eu-central-1' == task_definition.containers[0]['logConfiguration']['options']['awslogs-region']

def test_task_set_log_configurations_no_changes(task_definition):
    assert len(task_definition.containers[0]['logConfiguration']) == 0

    task_definition.set_log_configurations((('webserver', 'awslogs', 'awslogs-group', 'service_logs'), ('webserver', 'awslogs', 'awslogs-region', 'eu-central-1')))
    # deploy without log configurations does not change the previous configuration
    # needs to be actively changed
    task_definition.set_log_configurations(())

    assert len(task_definition.containers[0]['logConfiguration']) > 0

    assert('logDriver' in task_definition.containers[0]['logConfiguration'])
    assert 'awslogs' == task_definition.containers[0]['logConfiguration']['logDriver']
    assert 'options' in task_definition.containers[0]['logConfiguration']
    assert 'awslogs-group' in task_definition.containers[0]['logConfiguration']['options']
    assert 'service_logs' == task_definition.containers[0]['logConfiguration']['options']['awslogs-group']
    assert 'awslogs-region' in task_definition.containers[0]['logConfiguration']['options']
    assert 'eu-central-1' == task_definition.containers[0]['logConfiguration']['options']['awslogs-region']

def test_task_set_environment(task_definition):
    assert len(task_definition.containers[0]['environment']) == 3

    task_definition.set_environment((('webserver', 'foo', 'baz'), ('webserver', 'some-name', 'some-value')))

    assert len(task_definition.containers[0]['environment']) == 4

    assert {'name': 'lorem', 'value': 'ipsum'} in task_definition.containers[0]['environment']
    assert {'name': 'foo', 'value': 'baz'} in task_definition.containers[0]['environment']
    assert {'name': 'some-name', 'value': 'some-value'} in task_definition.containers[0]['environment']

def test_read_env_file_wrong_env_format():
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(b'#comment\n  \nIncompleteDescription')
    tmp.read()
    l = read_env_file('webserver',tmp.name)
    os.unlink(tmp.name)
    tmp.close()
    assert l == ()

def test_env_file_wrong_file_name():
    with pytest.raises(EcsTaskDefinitionCommandError):
        read_env_file('webserver','WrongFileName')

def test_task_set_environment_from_e_and_env_file(task_definition):
    assert len(task_definition.containers[0]['environment']) == 3

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(b'some-name-from-env-file=some-value-from-env-file')
    tmp.read()

    task_definition.set_environment((('webserver', 'foo', 'baz'), ('webserver', 'some-name', 'some-value')), env_file = (('webserver',tmp.name),))
    os.unlink(tmp.name)
    tmp.close()

    assert len(task_definition.containers[0]['environment']) == 5

    assert {'name': 'lorem', 'value': 'ipsum'} in task_definition.containers[0]['environment']
    assert {'name': 'foo', 'value': 'baz'} in task_definition.containers[0]['environment']
    assert {'name': 'some-name', 'value': 'some-value'} in task_definition.containers[0]['environment']
    assert {'name': 'some-name-from-env-file', 'value': 'some-value-from-env-file'} in task_definition.containers[0]['environment']

def test_task_set_environment_from_env_file(task_definition):
    assert len(task_definition.containers[0]['environment']) == 3

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(b'some-name-from-env-file=some-value-from-env-file')
    tmp.read()

    task_definition.set_environment((), env_file = (('webserver',tmp.name),))
    os.unlink(tmp.name)
    tmp.close()

    assert len(task_definition.containers[0]['environment']) == 4

    assert {'name': 'lorem', 'value': 'ipsum'} in task_definition.containers[0]['environment']
    assert {'name': 'some-name-from-env-file', 'value': 'some-value-from-env-file'} in task_definition.containers[0]['environment']


def test_task_set_environment_exclusively(task_definition):
    assert len(task_definition.containers[0]['environment']) == 3
    assert len(task_definition.containers[1]['environment']) == 0

    task_definition.set_environment((('application', 'foo', 'baz'), ('application', 'new-var', 'new-value')), exclusive=True)

    assert len(task_definition.containers[0]['environment']) == 0
    assert len(task_definition.containers[1]['environment']) == 2

    assert task_definition.containers[0]['environment'] == []
    assert {'name': 'foo', 'value': 'baz'} in task_definition.containers[1]['environment']
    assert {'name': 'new-var', 'value': 'new-value'} in task_definition.containers[1]['environment']


def test_task_set_docker_labels(task_definition):
    assert len(task_definition.containers[0]['dockerLabels']) == 3

    task_definition.set_docker_labels((('webserver', 'foo', 'baz'), ('webserver', 'some-name', 'some-value')))

    assert len(task_definition.containers[0]['dockerLabels']) == 4

    assert 'foo' in task_definition.containers[0]['dockerLabels']
    assert 'lorem' in task_definition.containers[0]['dockerLabels']
    assert 'some-name' in task_definition.containers[0]['dockerLabels']

def test_task_set_docker_label_exclusively(task_definition):
    assert len(task_definition.containers[0]['dockerLabels']) == 3
    assert len(task_definition.containers[1]['dockerLabels']) == 0

    task_definition.set_docker_labels((('application', 'foo', 'baz'), ('application', 'new-var', 'new-value')), exclusive=True)

    assert len(task_definition.containers[0]['dockerLabels']) == 0
    assert len(task_definition.containers[1]['dockerLabels']) == 2

    assert task_definition.containers[0]['dockerLabels'] == {}
    assert 'foo' in task_definition.containers[1]['dockerLabels']
    assert 'new-var' in task_definition.containers[1]['dockerLabels']

def test_task_set_s3_env_file_multiple_files(task_definition):
    assert len(task_definition.containers[0]['environmentFiles']) == 2

    task_definition.set_s3_env_file((('webserver', 'arn:aws:s3:::mycompany.domain.com/app/.env'), ('webserver', 'arn:aws:s3:::melted.cheese.com/grilled/.env'), ('proxyserver', 'arn:ars:s3:::pizza/dev/.env')))

    assert len(task_definition.containers[0]['environmentFiles']) == 4

    assert {'value': 'arn:aws:s3:::mycompany.domain.com/app/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']
    assert {'value': 'arn:aws:s3:::myS3bucket/myApp/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']
    assert {'value': 'arn:aws:s3:::coolBuckets/dev/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']
    assert {'value': 'arn:aws:s3:::melted.cheese.com/grilled/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']

def test_task_set_s3_env_file_single_file(task_definition):
    assert len(task_definition.containers[0]['environmentFiles']) == 2

    task_definition.set_s3_env_file(('webserver', 'arn:aws:s3:::mycompany.domain.com/app/.env'))

    assert len(task_definition.containers[0]['environmentFiles']) == 3
    # assert {'value': 'arn:aws:s3:::mycompany.domain.com/app/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']

def test_task_set_s3_env_file_exclusively(task_definition):
    assert len(task_definition.containers[0]['environmentFiles']) == 2

    task_definition.set_s3_env_file(('webserver', 'arn:aws:s3:::mycompany.domain.com/app/.env'), exclusive=True)

    assert len(task_definition.containers[0]['environmentFiles']) == 1

    assert {'value': 'arn:aws:s3:::mycompany.domain.com/app/.env', 'type': 's3'} in task_definition.containers[0]['environmentFiles']

def test_task_set_secrets_exclusively(task_definition):
    assert len(task_definition.containers[0]['secrets']) == 2

    task_definition.set_secrets((('webserver', 'new-secret', 'another-place'), ), exclusive=True)

    assert len(task_definition.containers[0]['secrets']) == 1
    assert {'name': 'new-secret', 'valueFrom': 'another-place'} in task_definition.containers[0]['secrets']


def test_task_set_secrets(task_definition):
    task_definition.set_secrets((('webserver', 'foo', 'baz'), ('webserver', 'some-name', 'some-value')))

    assert {'name': 'dolor', 'valueFrom': 'sit'} in task_definition.containers[0]['secrets']
    assert {'name': 'foo', 'valueFrom': 'baz'} in task_definition.containers[0]['secrets']
    assert {'name': 'some-name', 'valueFrom': 'some-value'} in task_definition.containers[0]['secrets']

def test_task_set_system_controls(task_definition):
    assert len(task_definition.containers[0]['systemControls']) == 1
    
    task_definition.set_system_controls((('webserver', 'net.core.somaxconn', '511'), ('webserver','net.ipv4.ip_forward', '1')))

    assert len(task_definition.containers[0]['systemControls']) == 2

    assert {'namespace': 'net.core.somaxconn', 'value': '511'} in task_definition.containers[0]['systemControls']
    assert {'namespace': 'net.ipv4.ip_forward', 'value': '1'} in task_definition.containers[0]['systemControls']

def test_task_set_system_controls_existing_not_set_again(task_definition):
    assert len(task_definition.containers[0]['systemControls']) == 1
    
    task_definition.set_system_controls((('webserver', 'net.ipv4.ip_forward', '1'), ))

    assert len(task_definition.containers[0]['systemControls']) == 2

    assert {'namespace': 'net.core.somaxconn', 'value': '511'} in task_definition.containers[0]['systemControls']
    assert {'namespace': 'net.ipv4.ip_forward', 'value': '1'} in task_definition.containers[0]['systemControls']

def test_task_set_system_controlsts_exclusively(task_definition):
    assert len(task_definition.containers[0]['systemControls']) == 1
    assert 'net.core.somaxconn' == task_definition.containers[0]['systemControls'][0]['namespace']
    
    task_definition.set_system_controls((('webserver', 'net.ipv4.ip_forward', '1'),), exclusive=True)

    assert len(task_definition.containers[0]['systemControls']) == 1

    assert 'net.ipv4.ip_forward' == task_definition.containers[0]['systemControls'][0]['namespace']
    assert {'namespace': 'net.ipv4.ip_forward', 'value': '1'} in task_definition.containers[0]['systemControls']

def test_task_set_ulimits(task_definition):
    assert len(task_definition.containers[0]['ulimits']) == 1
    
    task_definition.set_ulimits((('webserver', 'memlock', 256, 257), ('webserver', 'cpu', 80, 85)))

    assert len(task_definition.containers[0]['ulimits']) == 2

    assert {'name': 'memlock', 'softLimit': 256, 'hardLimit': 257} in task_definition.containers[0]['ulimits']
    assert {'name': 'cpu', 'softLimit': 80, 'hardLimit': 85} in task_definition.containers[0]['ulimits']

def test_task_set_ulimits_existing_not_set_again(task_definition):
    assert len(task_definition.containers[0]['ulimits']) == 1
    
    task_definition.set_ulimits((('webserver', 'cpu', 80, 85), ))

    assert len(task_definition.containers[0]['ulimits']) == 2

    assert {'name': 'memlock', 'softLimit': 256, 'hardLimit': 256} in task_definition.containers[0]['ulimits']
    assert {'name': 'cpu', 'softLimit': 80, 'hardLimit': 85} in task_definition.containers[0]['ulimits']

def test_task_set_ulimits_exclusively(task_definition):
    assert len(task_definition.containers[0]['ulimits']) == 1
    assert 'memlock' == task_definition.containers[0]['ulimits'][0]['name']
    
    task_definition.set_ulimits((('webserver', 'cpu', 80, 85),), exclusive=True)

    assert len(task_definition.containers[0]['ulimits']) == 1

    assert 'cpu' == task_definition.containers[0]['ulimits'][0]['name']
    assert {'name': 'cpu', 'softLimit': 80, 'hardLimit': 85} in task_definition.containers[0]['ulimits']

def test_task_set_port_mappings(task_definition):
    assert len(task_definition.containers[0]['portMappings']) == 1
    assert 8080 == task_definition.containers[0]['portMappings'][0]['containerPort']
    
    task_definition.set_port_mappings((('webserver', 8080, 8080), ('webserver', 81, 80)))

    assert len(task_definition.containers[0]['portMappings']) == 2

    assert {'containerPort': 8080, 'hostPort': 8080, 'protocol': 'tcp'} in task_definition.containers[0]['portMappings']
    assert {'containerPort': 81, 'hostPort': 80, 'protocol': 'tcp'} in task_definition.containers[0]['portMappings']

def test_task_set_port_mappings_exclusively(task_definition):
    assert len(task_definition.containers[0]['portMappings']) == 1
    assert 8080 == task_definition.containers[0]['portMappings'][0]['containerPort']
    
    task_definition.set_port_mappings((('webserver', 81, 80),), exclusive=True)

    assert len(task_definition.containers[0]['portMappings']) == 1

    assert 81 == task_definition.containers[0]['portMappings'][0]['containerPort']
    assert {'containerPort': 81, 'hostPort': 80, 'protocol': 'tcp'} in task_definition.containers[0]['portMappings']

def test_task_set_mount_points(task_definition):
    assert len(task_definition.containers[0]['mountPoints']) == 1
    assert '/container/path' == task_definition.containers[0]['mountPoints'][0]['containerPath']
    
    task_definition.set_mount_points((('webserver', 'volume', '/data/path'), ('webserver', 'another_volume', '/logs/path')))

    assert len(task_definition.containers[0]['mountPoints']) == 2

    assert {'sourceVolume': 'volume', 'containerPath': '/data/path', 'readOnly': False} in task_definition.containers[0]['mountPoints']
    assert {'sourceVolume': 'another_volume', 'containerPath': '/logs/path', 'readOnly': False} in task_definition.containers[0]['mountPoints']

def test_task_set_task_cpu(task_definition):
    assert task_definition.cpu is None
    task_definition.set_task_cpu(256)
    assert task_definition.cpu == '256'

def test_task_set_task_memory(task_definition):
    assert task_definition.memory is None
    task_definition.set_task_memory(1024)
    assert task_definition.memory == '1024'

def test_task_set_mount_points_exclusively(task_definition):
    assert len(task_definition.containers[0]['mountPoints']) == 1
    assert '/container/path' == task_definition.containers[0]['mountPoints'][0]['containerPath']
    assert 'volume' == task_definition.containers[0]['mountPoints'][0]['sourceVolume']
    
    task_definition.set_mount_points((('webserver', 'another_volume', '/logs/path'),), exclusive=True)

    assert len(task_definition.containers[0]['mountPoints']) == 1

    assert '/logs/path' == task_definition.containers[0]['mountPoints'][0]['containerPath']
    assert 'another_volume' == task_definition.containers[0]['mountPoints'][0]['sourceVolume']
    assert {'sourceVolume': 'another_volume', 'containerPath': '/logs/path', 'readOnly': False} in task_definition.containers[0]['mountPoints']

def test_task_set_image_for_unknown_container(task_definition):
    with pytest.raises(UnknownContainerError):
        task_definition.set_images(foobar='new-image:123')


def test_task_set_command(task_definition):
    task_definition.set_commands(webserver='run-webserver', application='run-application')
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['command'] == ['run-webserver']
        if container['name'] == 'application':
            assert container['command'] == ['run-application']


def test_task_set_command_with_multiple_arguments(task_definition):
    task_definition.set_commands(webserver='run-webserver arg1 arg2', application='run-application arg1 arg2')
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['command'] == ['run-webserver', 'arg1', 'arg2']
        if container['name'] == 'application':
            assert container['command'] == ['run-application', 'arg1', 'arg2']

def test_task_set_command_with_empty_argument(task_definition):
    empty_argument = " "
    task_definition.set_commands(webserver=empty_argument + 'run-webserver arg1 arg2')
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['command'] == ['run-webserver', 'arg1', 'arg2']

def test_task_set_command_as_json_list(task_definition):
    task_definition.set_commands(webserver='["run-webserver", "arg1", "arg2"]', application='["run-application", "arg1", "arg2"]')
    for container in task_definition.containers:
        if container['name'] == 'webserver':
            assert container['command'] == ['run-webserver', 'arg1', 'arg2']
        if container['name'] == 'application':
            assert container['command'] == ['run-application', 'arg1', 'arg2']

def test_task_set_command_as_invalid_json_list(task_definition):
    with pytest.raises(EcsTaskDefinitionCommandError):
        task_definition.set_commands(webserver='["run-webserver, "arg1" arg2"]', application='["run-application" "arg1 "arg2"]')


def test_task_set_command_for_unknown_container(task_definition):
    with pytest.raises(UnknownContainerError):
        task_definition.set_images(foobar='run-foobar')


class TestSetHealthChecks:
    @pytest.mark.parametrize(
        'webserver_health_check, application_health_check',
        (
            (
                ('webserver', 'curl -f http://webserver/alive/', 30, 5, 3, 0),
                ('application', 'curl -f http://application/alive/', 60, 10, 6, 5)
            ),
            (
                ('webserver', 'curl -f http://webserver/alive/', 30, 5, 3, 0),
                ('application', 'curl -f http://application/alive/', 60, 10, 6, 5)
            )
        )
    )
    def test_success(self, webserver_health_check, application_health_check, task_definition):        
        task_definition.set_health_checks((
            webserver_health_check,
            application_health_check,
        ))
        for container in task_definition.containers:
            if container['name'] == 'webserver':
                assert container['healthCheck'] == {
                    'command': ['CMD-SHELL', 'curl -f http://webserver/alive/'],
                    'interval': 30,
                    'timeout': 5,
                    'retries': 3,
                    'startPeriod': 0
                }
            if container['name'] == 'application':
                assert container['healthCheck'] == {
                    'command': ['CMD-SHELL', 'curl -f http://application/alive/'],
                    'interval': 60,
                    'timeout': 10,
                    'retries': 6,
                    'startPeriod': 5
                }

    def test_unknown_container(self, task_definition):
        with pytest.raises(UnknownContainerError):
            task_definition.set_health_checks((('foobar', 'curl -f http://application/alive/', 60, 10, 6,  5),))

def test_task_get_overrides(task_definition):
    assert task_definition.get_overrides() == []


def test_task_get_overrides_with_command(task_definition):
    task_definition.set_commands(webserver='/usr/bin/python script.py')
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['command'] == ['/usr/bin/python','script.py']


def test_task_get_overrides_with_environment(task_definition):
    task_definition.set_environment((('webserver', 'foo', 'baz'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['name'] == 'webserver'
    assert dict(name='foo', value='baz') in overrides[0]['environment']


def test_task_get_overrides_with_docker_labels(task_definition):
    task_definition.set_docker_labels((('webserver', 'foo', 'baz'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['name'] == 'webserver'
    #assert 'foo' in overrides[0]['dockerLabels']
    assert overrides[0]['dockerLabels']['foo'] == 'baz'


def test_task_get_overrides_with_secrets(task_definition):
    task_definition.set_secrets((('webserver', 'foo', 'baz'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['name'] == 'webserver'
    assert dict(name='foo', valueFrom='baz') in overrides[0]['secrets']


def test_task_get_overrides_with_command_environment_and_secrets(task_definition):
    task_definition.set_commands(webserver='/usr/bin/python script.py')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))
    task_definition.set_secrets((('webserver', 'bar', 'qux'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['name'] == 'webserver'
    assert overrides[0]['command'] == ['/usr/bin/python','script.py']
    assert dict(name='foo', value='baz') in overrides[0]['environment']
    assert dict(name='bar', valueFrom='qux') in overrides[0]['secrets']


def test_task_get_overrides_with_command_secrets_and_environment_for_multiple_containers(task_definition):
    task_definition.set_commands(application='/usr/bin/python script.py')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))
    task_definition.set_secrets((('webserver', 'bar', 'qux'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 2
    assert overrides[0]['name'] == 'application'
    assert overrides[0]['command'] == ['/usr/bin/python','script.py']
    assert overrides[1]['name'] == 'webserver'
    assert dict(name='foo', value='baz') in overrides[1]['environment']
    assert dict(name='bar', valueFrom='qux') in overrides[1]['secrets']


def test_task_get_overrides_command(task_definition):
    command = task_definition.get_overrides_command('/usr/bin/python script.py')
    assert isinstance(command, list)
    assert command == ['/usr/bin/python','script.py']


def test_task_get_overrides_environment(task_definition):
    environment = task_definition.get_overrides_env(dict(foo='bar'))
    assert isinstance(environment, list)
    assert len(environment) == 1
    assert environment[0] == dict(name='foo', value='bar')


def test_task_get_overrides_docker_labels(task_definition):
    dockerlabels = task_definition.get_overrides_docker_labels(dict(foo='bar'))
    assert isinstance(dockerlabels, dict)
    assert len(dockerlabels) == 1
    assert dockerlabels['foo'] == 'bar'


def test_task_get_overrides_secrets(task_definition):
    secrets = task_definition.get_overrides_secrets(dict(foo='bar'))
    assert isinstance(secrets, list)
    assert len(secrets) == 1
    assert secrets[0] == dict(name='foo', valueFrom='bar')


def test_task_definition_diff():
    diff = EcsTaskDefinitionDiff('webserver', 'image', 'new', 'old')
    assert str(diff) == 'Changed image of container "webserver" to: "new" (was: "old")'


@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def test_client_init(mocked_init, mocked_client):
    mocked_init.return_value = None

    EcsClient('access_key_id', 'secret_access_key', 'region', 'profile', 'session_token')

    mocked_init.assert_called_once_with(aws_access_key_id='access_key_id',
                                        aws_secret_access_key='secret_access_key',
                                        profile_name='profile',
                                        region_name='region',
                                        aws_session_token='session_token')
    mocked_client.assert_any_call('ecs')
    mocked_client.assert_any_call('events')


@pytest.fixture
@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def client(mocked_init, mocked_client):
    mocked_init.return_value = None
    return EcsClient('access_key_id', 'secret_access_key', 'region', 'profile', 'session_token')


def test_client_describe_services(client):
    client.describe_services('test-cluster', 'test-service')
    client.boto.describe_services.assert_called_once_with(cluster='test-cluster', services=['test-service'])


def test_client_describe_task_definition(client):
    client.describe_task_definition('task_definition_arn')
    client.boto.describe_task_definition.assert_called_once_with(include=['TAGS'], taskDefinition='task_definition_arn')


def test_client_describe_unknown_task_definition(client):
    error_response = {'Error': {'Code': 'ClientException', 'Message': 'Unable to describe task definition.'}}
    client.boto.describe_task_definition.side_effect = ClientError(error_response, 'DescribeServices')
    with pytest.raises(UnknownTaskDefinitionError):
        client.describe_task_definition('task_definition_arn')


def test_client_list_tasks(client):
    client.list_tasks('test-cluster', 'test-service')
    client.boto.list_tasks.assert_called_once_with(cluster='test-cluster', serviceName='test-service')


def test_client_describe_tasks(client):
    client.describe_tasks('test-cluster', 'task-arns')
    client.boto.describe_tasks.assert_called_once_with(cluster='test-cluster', tasks='task-arns')


def test_client_register_task_definition(client):
    containers = [{'name': 'foo'}]
    volumes = [{'foo': 'bar'}]
    role_arn = 'arn:test:role'
    execution_role_arn = 'arn:test:role'
    runtime_platform = {'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'}
    task_definition = EcsTaskDefinition(
        containerDefinitions=containers,
        volumes=volumes,
        family='family',
        revision=1,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        runtimePlatform=runtime_platform,
        tags={
            'Name': 'test_client_register_task_definition'
        },
        status='active',
        taskDefinitionArn='arn:task',
        requiresAttributes={},
        unkownProperty='foobar',
        cpu=256,
        memory=1024
    )

    client.register_task_definition(
        family=task_definition.family,
        containers=task_definition.containers,
        volumes=task_definition.volumes,
        role_arn=task_definition.role_arn,
        execution_role_arn=execution_role_arn,
        runtime_platform=task_definition.runtime_platform,
        tags=task_definition.tags,
        additional_properties=task_definition.additional_properties,
        cpu=256,
        memory=1024
    )

    client.boto.register_task_definition.assert_called_once_with(
        family='family',
        containerDefinitions=containers,
        volumes=volumes,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        runtimePlatform=runtime_platform,
        tags=task_definition.tags,
        unkownProperty='foobar',
        cpu=256,
        memory=1024
    )


def test_client_register_task_definition_without_optional_values(client):
    containers = [{'name': 'foo'}]
    volumes = [{'foo': 'bar'}]
    role_arn = 'arn:test:role'
    execution_role_arn = 'arn:test:role'
    runtime_platform = {'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'}
    task_definition = EcsTaskDefinition(
        containerDefinitions=containers,
        volumes=volumes,
        family='family',
        revision=1,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        tags={
            'Name': 'test_client_register_task_definition'
        },
        status='active',
        taskDefinitionArn='arn:task',
        requiresAttributes={},
    )

    client.register_task_definition(
        family=task_definition.family,
        containers=task_definition.containers,
        volumes=task_definition.volumes,
        role_arn=task_definition.role_arn,
        execution_role_arn=execution_role_arn,
        tags=task_definition.tags,
        additional_properties=task_definition.additional_properties,
        runtime_platform=None,
        cpu=None,
        memory=None
    )

    client.boto.register_task_definition.assert_called_once_with(
        family='family',
        containerDefinitions=containers,
        volumes=volumes,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        tags=task_definition.tags,
    )


def test_client_register_task_definition_without_tags(client):
    containers = [{'name': 'foo'}]
    volumes = [{'foo': 'bar'}]
    role_arn = 'arn:test:role'
    execution_role_arn = 'arn:test:role'
    runtime_platform = {'cpuArchitecture': 'X86_64', 'operatingSystemFamily': 'LINUX'}
    task_definition = EcsTaskDefinition(
        containerDefinitions=containers,
        volumes=volumes,
        family='family',
        revision=1,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        runtimePlatform=runtime_platform,
        tags={},
        status='active',
        taskDefinitionArn='arn:task',
        requiresAttributes={},
        unkownProperty='foobar'
    )

    client.register_task_definition(
        family=task_definition.family,
        containers=task_definition.containers,
        volumes=task_definition.volumes,
        role_arn=task_definition.role_arn,
        execution_role_arn=execution_role_arn,
        runtime_platform=task_definition.runtime_platform,
        tags=task_definition.tags,
        additional_properties=task_definition.additional_properties,
        cpu=256,
        memory=1024
    )

    client.boto.register_task_definition.assert_called_once_with(
        family='family',
        containerDefinitions=containers,
        volumes=volumes,
        taskRoleArn=role_arn,
        executionRoleArn=execution_role_arn,
        runtimePlatform=runtime_platform,
        unkownProperty='foobar',
        cpu=256,
        memory=1024
    )


def test_client_deregister_task_definition(client):
    client.deregister_task_definition('task_definition_arn')
    client.boto.deregister_task_definition.assert_called_once_with(taskDefinition='task_definition_arn')


def test_client_update_service(client):
    client.update_service('test-cluster', 'test-service', 5, 'task-definition')
    client.boto.update_service.assert_called_once_with(
        cluster='test-cluster',
        service='test-service',
        desiredCount=5,
        taskDefinition='task-definition'
    )


def test_client_update_service_without_desired_count(client):
    client.update_service('test-cluster', 'test-service', None, 'task-definition')
    client.boto.update_service.assert_called_once_with(
        cluster='test-cluster',
        service='test-service',
        taskDefinition='task-definition'
    )


def test_client_run_task(client):
    client.run_task(
        cluster='test-cluster',
        task_definition='test-task',
        count=2,
        started_by='test',
        overrides=dict(foo='bar')
    )

    client.boto.run_task.assert_called_once_with(
        cluster='test-cluster',
        taskDefinition='test-task',
        count=2,
        startedBy='test',
        overrides=dict(foo='bar')
    )


def test_ecs_action_init(client):
    action = EcsAction(client, 'test-cluster', 'test-service')
    assert action.client == client
    assert action.cluster_name == 'test-cluster'
    assert action.service_name == 'test-service'
    assert isinstance(action.service, EcsService)


def test_ecs_action_init_with_invalid_cluster():
    with pytest.raises(EcsConnectionError) as excinfo:
        client = EcsTestClient('access_key',  'secret_key')
        EcsAction(client, 'invliad-cluster', 'test-service')
    assert str(excinfo.value) == 'An error occurred (ClusterNotFoundException) when calling the DescribeServices ' \
                                 'operation: Cluster not found.'


def test_ecs_action_init_with_invalid_service():
    with pytest.raises(EcsConnectionError) as excinfo:
        client = EcsTestClient('access_key',  'secret_key')
        EcsAction(client, 'test-cluster', 'invalid-service')
    assert str(excinfo.value) == 'An error occurred when calling the DescribeServices operation: Service not found.'


def test_ecs_action_init_without_credentials():
    with pytest.raises(EcsConnectionError) as excinfo:
        client = EcsTestClient()
        EcsAction(client, 'test-cluster', 'invalid-service')
    assert str(excinfo.value) == 'Unable to locate credentials. Configure credentials by running "aws configure".'


def test_ecs_action_get_service():
    client = EcsTestClient('access_key', 'secret_key')
    action = EcsAction(client, 'test-cluster', 'test-service')
    service = action.get_service()
    assert service.name == 'test-service'
    assert service.cluster == 'test-cluster'


@patch.object(EcsClient, '__init__')
def test_ecs_action_get_current_task_definition(client, service):
    client.describe_task_definition.return_value = RESPONSE_TASK_DEFINITION

    action = EcsAction(client, 'test-cluster', 'test-service')
    task_definition = action.get_current_task_definition(service)

    client.describe_task_definition.assert_called_once_with(
        task_definition_arn=service.task_definition
    )

    assert isinstance(task_definition, EcsTaskDefinition)
    assert task_definition.family == 'test-task'
    assert task_definition.revision == 1
    assert task_definition.arn == 'arn:aws:ecs:eu-central-1:123456789012:task-definition/test-task:1'


@patch.object(EcsClient, '__init__')
def test_update_task_definition(client, task_definition):
    client.register_task_definition.return_value = RESPONSE_TASK_DEFINITION

    action = EcsAction(client, 'test-cluster', 'test-service')
    new_task_definition = action.update_task_definition(task_definition)

    assert isinstance(new_task_definition, EcsTaskDefinition)
    client.register_task_definition.assert_called_once_with(
        family=task_definition.family,
        containers=task_definition.containers,
        volumes=task_definition.volumes,
        role_arn=task_definition.role_arn,
        execution_role_arn=task_definition.execution_role_arn,
        runtime_platform=task_definition.runtime_platform,
        tags=task_definition.tags,
        additional_properties={
            'networkMode': 'host',
            'placementConstraints': {},
            'unknownProperty': 'lorem-ipsum'
        },
        cpu=None,
        memory=None
    )


@patch.object(EcsClient, '__init__')
def test_deregister_task_definition(client, task_definition):
    action = EcsAction(client, 'test-cluster', 'test-service')
    action.deregister_task_definition(task_definition)

    client.deregister_task_definition.assert_called_once_with(
        task_definition.arn
    )


@patch.object(EcsClient, '__init__')
def test_update_service(client, service):
    client.update_service.return_value = RESPONSE_SERVICE

    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    new_service = action.update_service(service)

    assert isinstance(new_service, EcsService)
    client.update_service.assert_called_once_with(
        cluster=service.cluster,
        service=service.name,
        desired_count=None,
        task_definition=service.task_definition
    )


@patch.object(EcsClient, '__init__')
def test_is_deployed(client, service):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_1
    client.describe_tasks.return_value = RESPONSE_DESCRIBE_TASKS

    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    is_deployed = action.is_deployed(service)

    assert is_deployed is True
    client.list_tasks.assert_called_once_with(
        cluster_name=service.cluster,
        service_name=service.name
    )


@patch.object(EcsClient, '__init__')
def test_is_not_deployed_with_more_than_one_deployment(client, service):
    service['deployments'].append(service['deployments'][0])

    client.list_tasks.return_value = RESPONSE_LIST_TASKS_1
    client.describe_tasks.return_value = RESPONSE_DESCRIBE_TASKS

    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    is_deployed = action.is_deployed(service)

    assert is_deployed is False


@patch.object(EcsClient, '__init__')
def test_is_deployed_if_no_tasks_should_be_running(client, service):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_0
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    service['desiredCount'] = 0
    is_deployed = action.is_deployed(service)
    assert is_deployed is True


@patch.object(EcsClient, '__init__')
def test_is_not_deployed_if_no_tasks_running(client, service):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_0
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    is_deployed = action.is_deployed(service)
    assert is_deployed is False


@patch.object(EcsClient, '__init__')
def test_is_not_deployed_if_deployment_failed(client, service_with_failed_deployment):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_0
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    with pytest.raises(EcsDeploymentError):
        action.is_deployed(service_with_failed_deployment)


@patch('ecs_deploy.ecs.logger')
@patch.object(EcsClient, '__init__')
def test_is_not_deployed_with_failed_tasks(client, logger, service_with_failed_tasks):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_0
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    action.is_deployed(service_with_failed_tasks)
    logger.warning.assert_called_once_with('3 tasks failed to start')


@patch.object(EcsClient, '__init__')
def test_get_running_tasks_count(client, service):
    client.describe_tasks.return_value = RESPONSE_DESCRIBE_TASKS
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    running_count = action.get_running_tasks_count(service, [TASK_ARN_1, TASK_ARN_2])
    assert running_count == 2


@patch.object(EcsClient, '__init__')
def test_get_running_tasks_count_new_revision(client, service, task_definition_revision_2):
    client.describe_tasks.return_value = RESPONSE_DESCRIBE_TASKS
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    service.set_task_definition(task_definition_revision_2)
    running_count = action.get_running_tasks_count(service, [TASK_ARN_1, TASK_ARN_2])
    assert running_count == 0


@patch.object(EcsClient, '__init__')
def test_deploy_action(client, task_definition_revision_2):
    action = DeployAction(client, CLUSTER_NAME, SERVICE_NAME)
    updated_service = action.deploy(task_definition_revision_2)

    assert action.service.task_definition == task_definition_revision_2.arn
    assert isinstance(updated_service, EcsService)

    client.describe_services.assert_called_once_with(
        cluster_name=CLUSTER_NAME,
        service_name=SERVICE_NAME
    )
    client.update_service.assert_called_once_with(
        cluster=action.service.cluster,
        service=action.service.name,
        desired_count=action.service.desired_count,
        task_definition=task_definition_revision_2.arn
    )


@patch.object(EcsClient, '__init__')
def test_scale_action(client):
    action = ScaleAction(client, CLUSTER_NAME, SERVICE_NAME)
    updated_service = action.scale(5)

    assert isinstance(updated_service, EcsService)

    client.describe_services.assert_called_once_with(
        cluster_name=CLUSTER_NAME,
        service_name=SERVICE_NAME
    )
    client.update_service.assert_called_once_with(
        cluster=action.service.cluster,
        service=action.service.name,
        desired_count=5,
        task_definition=action.service.task_definition
    )


@patch.object(EcsClient, '__init__')
def test_run_action(client):
    action = RunAction(client, CLUSTER_NAME)
    assert len(action.started_tasks) == 0


@patch.object(EcsClient, '__init__')
def test_run_action_run(client, task_definition):
    action = RunAction(client, CLUSTER_NAME)
    client.run_task.return_value = dict(tasks=[dict(taskArn='A'), dict(taskArn='B')])
    action.run(task_definition, 2, 'test', LAUNCH_TYPE_EC2, (), (), False, None)

    client.run_task.assert_called_once_with(
        cluster=CLUSTER_NAME,
        task_definition=task_definition.family_revision,
        count=2,
        started_by='test',
        overrides=dict(containerOverrides=task_definition.get_overrides()),
        launchtype=LAUNCH_TYPE_EC2,
        subnets=(),
        security_groups=(),
        public_ip=False,
        platform_version=None,
    )

    assert len(action.started_tasks) == 2


def test_ecs_server_get_warnings():
    since = datetime.now() - timedelta(hours=1)
    until = datetime.now() + timedelta(hours=1)

    event_unable = {
        'createdAt': datetime.now(),
        'message': 'unable to foo',
    }

    event_unknown = {
        'createdAt': datetime.now(),
        'message': 'unkown foo',
    }

    service = EcsService('foo', {
        'deployments': [],
        'events': [event_unable, event_unknown],
    })

    assert len(service.get_warnings(since, until)) == 1


def test_init_deployment():
    service = EcsService('foo', PAYLOAD_SERVICE)
    assert service.primary_deployment.has_failed is False
    assert service.primary_deployment.has_completed is True
    assert service.active_deployment.has_failed is False
    assert service.active_deployment.has_completed is True
    assert service.active_deployment == service.primary_deployment


def test_init_deployment_in_progress():
    service = EcsService('foo', PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_IN_PROGRESS)
    assert service.primary_deployment.has_failed is False
    assert service.primary_deployment.has_completed is False
    assert service.active_deployment.has_failed is False
    assert service.active_deployment.has_completed is True
    assert service.active_deployment != service.primary_deployment


def test_init_deployment_failed_no_rollback():
    service = EcsService('foo', PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_FAILED_NO_ROLLBACK)
    assert service.primary_deployment.has_failed is True
    assert service.primary_deployment.has_completed is False
    assert service.active_deployment.has_failed is False
    assert service.active_deployment.has_completed is True
    assert service.active_deployment != service.primary_deployment


def test_init_deployment_failed_with_rollback():
    service = EcsService('foo', PAYLOAD_SERVICE_WITHOUT_DEPLOYMENT_FAILED_WITH_ROLLBACK)
    assert service.primary_deployment.has_failed is False
    assert service.primary_deployment.has_completed is False
    assert service.active_deployment.has_failed is True
    assert service.active_deployment.has_completed is False
    assert service.active_deployment != service.primary_deployment


def test_deployment_primary():
    deployment = EcsDeployment(PAYLOAD_DEPLOYMENTS_IN_PROGRESS[0])
    assert deployment.is_primary is True
    assert deployment.is_active is False


def test_deployment_active():
    deployment = EcsDeployment(PAYLOAD_DEPLOYMENTS_IN_PROGRESS[1])
    assert deployment.is_active is True
    assert deployment.is_primary is False


def test_deployment_failed():
    deployment = EcsDeployment(PAYLOAD_DEPLOYMENTS_FAILED[0])
    assert deployment.has_failed is True
    assert deployment.has_completed is False
    assert deployment.failed_tasks > 0


def test_deployment_completed():
    deployment = EcsDeployment(PAYLOAD_DEPLOYMENTS_FAILED[1])
    assert deployment.has_completed is True
    assert deployment.has_failed is False
    assert deployment.failed_tasks == 0


def test_deployment_rollout_state_reason():
    deployment = EcsDeployment(PAYLOAD_DEPLOYMENTS_FAILED[0])
    assert deployment.rollout_state_reason == "ECS deployment circuit breaker: tasks failed to start."


class EcsTestClient:
    def __init__(self, access_key_id=None, secret_access_key=None, region=None,
                 profile=None, deployment_errors=False, client_errors=False,
                 wait=0):
        super().__init__()
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.profile = profile
        self.deployment_errors = deployment_errors
        self.client_errors = client_errors
        self.wait_until = datetime.now() + timedelta(seconds=wait)

    def describe_services(self, cluster_name, service_name):
        if not self.access_key_id or not self.secret_access_key:
            raise NoCredentialsError()
        if cluster_name != 'test-cluster':
            error_response = {'Error': {'Code': 'ClusterNotFoundException', 'Message': 'Cluster not found.'}}
            raise ClientError(error_response, 'DescribeServices')
        if service_name != 'test-service':
            return {'services': []}
        if self.deployment_errors:
            return {
                "services": [PAYLOAD_SERVICE_WITH_ERRORS],
                "failures": []
            }
        return {
            "services": [PAYLOAD_SERVICE],
            "failures": []
        }

    def describe_task_definition(self, task_definition_arn):
        if not self.access_key_id or not self.secret_access_key:
            raise EcsConnectionError('Unable to locate credentials. Configure credentials by running "aws configure".')
        if task_definition_arn in RESPONSE_TASK_DEFINITIONS:
            return deepcopy(RESPONSE_TASK_DEFINITIONS[task_definition_arn])
        raise UnknownTaskDefinitionError('Unknown task definition arn: %s' % task_definition_arn)

    def list_tasks(self, cluster_name, service_name):
        if self.wait_until <= datetime.now():
            return deepcopy(RESPONSE_LIST_TASKS_2)
        return deepcopy(RESPONSE_LIST_TASKS_0)

    def describe_tasks(self, cluster_name, task_arns):
        return deepcopy(RESPONSE_DESCRIBE_TASKS)

    def register_task_definition(self, family, containers, volumes, role_arn,
                                 execution_role_arn, runtime_platform, tags, cpu, memory, additional_properties):
        if not self.access_key_id or not self.secret_access_key:
            raise EcsConnectionError('Unable to locate credentials. Configure credentials by running "aws configure".')
        return deepcopy(RESPONSE_TASK_DEFINITION_2)

    def deregister_task_definition(self, task_definition_arn):
        return deepcopy(RESPONSE_TASK_DEFINITION)

    def update_service(self, cluster, service, desired_count, task_definition):
        if self.client_errors:
            error = dict(Error=dict(Code=123, Message="Something went wrong"))
            raise ClientError(error, 'fake_error')
        if self.deployment_errors:
            return deepcopy(RESPONSE_SERVICE_WITH_ERRORS)
        return deepcopy(RESPONSE_SERVICE)

    def run_task(self, cluster, task_definition, count, started_by, overrides,
                 launchtype='EC2', subnets=(), security_groups=(),
                 public_ip=False, platform_version=None):
        if not self.access_key_id or not self.secret_access_key:
            raise EcsConnectionError('Unable to locate credentials. Configure credentials by running "aws configure".')
        if cluster == 'unknown-cluster':
            raise EcsConnectionError('An error occurred (ClusterNotFoundException) when calling the RunTask operation: Cluster not found.')
        if self.deployment_errors:
            error = dict(Error=dict(Code=123, Message="Something went wrong"))
            raise ClientError(error, 'fake_error')
        return dict(tasks=[dict(taskArn='arn:foo:bar'), dict(taskArn='arn:lorem:ipsum')])

    def update_rule(self, cluster, rule, task_definition):
        if not self.access_key_id or not self.secret_access_key:
            raise EcsConnectionError('Unable to locate credentials. Configure credentials by running "aws configure".')
        if cluster == 'unknown-cluster':
            raise EcsConnectionError('An error occurred (ClusterNotFoundException) when calling the RunTask operation: Cluster not found.')
