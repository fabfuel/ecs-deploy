from copy import deepcopy

import pytest
import datetime

from boto3.session import Session
from dateutil.tz import tzlocal
from mock.mock import patch

from ecs_deploy.ecs import EcsService, EcsTaskDefinition, UnknownContainerError, EcsTaskDefinitionDiff, EcsClient

CLUSTER_NAME = u'test-cluster'
SERVICE_NAME = u'test-service'
DESIRED_COUNT = 4
TASK_1_FAMILY = u'test'
TASK_1_REVISION = 1
TASK_1_ARN = u'arn:aws:ecs:eu-central-1:123456789:task-definition/%s:%s' % (TASK_1_FAMILY, TASK_1_REVISION)
TASK_2_FAMILY = u'test'
TASK_2_REVISION = 2
TASK_2_ARN = u'arn:aws:ecs:eu-central-1:123456789:task-definition/%s:%s' % (TASK_2_FAMILY, TASK_2_REVISION)
TASK_2_VOLUMES = []
TASK_2_CONTAINERS = [
    {u'name': u'webserver', u'image': u'webserver:123', u'command': u'run'},
    {u'name': u'application', u'image': u'application:123', u'command': u'run'}
]


@pytest.fixture
def task_definition_payload():
    return {
        u'arn': TASK_2_ARN,
        u'family': TASK_2_FAMILY,
        u'revision': TASK_2_REVISION,
        u'volumes': deepcopy(TASK_2_VOLUMES),
        u'containerDefinitions': deepcopy(TASK_2_CONTAINERS),
    }


@pytest.fixture
def task_definition(task_definition_payload):
    return EcsTaskDefinition(task_definition_payload)


@pytest.fixture
def deployment_payload():
    return [
        {
            u'status': u'ACTIVE',
            u'pendingCount': 0,
            u'desiredCount': DESIRED_COUNT - 1,
            u'runningCount': DESIRED_COUNT - 1,
            u'taskDefinition': TASK_1_ARN,
            u'createdAt': datetime.datetime(2016, 3, 10, 12, 00, 00, 000000, tzinfo=tzlocal()),
            u'updatedAt': datetime.datetime(2016, 3, 10, 12, 5, 00, 000000, tzinfo=tzlocal()),
            u'id': u'ecs-svc/0000000000000000001',
        },
        {
            u'status': u'PRIMARY',
            u'pendingCount': 0,
            u'desiredCount': DESIRED_COUNT,
            u'runningCount': DESIRED_COUNT,
            u'taskDefinition': TASK_1_ARN,
            u'createdAt': datetime.datetime(2016, 3, 11, 12, 00, 00, 000000, tzinfo=tzlocal()),
            u'updatedAt': datetime.datetime(2016, 3, 11, 12, 5, 00, 000000, tzinfo=tzlocal()),
            u'id': u'ecs-svc/0000000000000000002',
        }
    ]


@pytest.fixture
def service_payload(deployment_payload):
    return {
        'serviceName': SERVICE_NAME,
        'desiredCount': DESIRED_COUNT,
        'taskDefinition': TASK_1_ARN,
        'deployments': deployment_payload
    }


@pytest.fixture
def service_payload_without_deployments():
    return {
        'serviceName': SERVICE_NAME,
        'desiredCount': DESIRED_COUNT,
        'taskDefinition': TASK_1_ARN,
        'deployments': []
    }


@pytest.fixture
def service(service_payload):
    return EcsService(CLUSTER_NAME, service_payload)


@pytest.fixture
def service_without_deployments(service_payload_without_deployments):
    return EcsService(CLUSTER_NAME, service_payload_without_deployments)


def test_service_init(service):
    assert isinstance(service, dict)
    assert service.cluster == CLUSTER_NAME
    assert service['desiredCount'] == DESIRED_COUNT
    assert service['taskDefinition'] == TASK_1_ARN


def test_service_set_desired_count(service):
    assert service.desired_count == DESIRED_COUNT
    service.set_desired_count(5)
    assert service.desired_count == 5


def test_service_set_task_definition(service, task_definition):
    assert service.task_definition == TASK_1_ARN
    service.set_task_definition(task_definition)
    assert service.task_definition == task_definition.arn


def test_service_name(service):
    assert service.name == SERVICE_NAME


def test_service_deployment_created_at(service):
    assert service.deployment_created_at == datetime.datetime(2016, 3, 11, 12, 00, 00, 000000, tzinfo=tzlocal())


def test_service_deployment_updated_at(service):
    assert service.deployment_updated_at == datetime.datetime(2016, 3, 11, 12, 5, 00, 000000, tzinfo=tzlocal())


def test_service_deployment_created_at_without_deployments(service_without_deployments):
    now = datetime.datetime.now()
    assert service_without_deployments.deployment_created_at >= now
    assert service_without_deployments.deployment_created_at <= datetime.datetime.now()


def test_service_deployment_updated_at_without_deployments(service_without_deployments):
    now = datetime.datetime.now()
    assert service_without_deployments.deployment_updated_at >= now
    assert service_without_deployments.deployment_updated_at <= datetime.datetime.now()


def test_task_family(task_definition):
    assert task_definition.family == TASK_1_FAMILY


def test_task_containers(task_definition):
    assert task_definition.containers == TASK_2_CONTAINERS


def test_task_container_names(task_definition):
    assert 'webserver' in task_definition.container_names
    assert 'application' in task_definition.container_names
    assert 'foobar' not in task_definition.container_names


def test_task_volumes(task_definition):
    assert task_definition.volumes == TASK_2_VOLUMES


def test_task_revision(task_definition):
    assert task_definition.revision == TASK_2_REVISION


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


def test_task_set_command_for_unknown_container(task_definition):
    with pytest.raises(UnknownContainerError):
        task_definition.set_images(foobar='run-foobar')


def test_task_definition_diff():
    diff = EcsTaskDefinitionDiff('webserver', 'image', 'new', 'old')
    assert str(diff) == "Changed image of container 'webserver' to: new (was: old)"


@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def test_client_init(mocked_init, mocked_client):
    mocked_init.return_value = None

    EcsClient('access_key_id', 'secret_access_key', 'region', 'profile')

    mocked_init.assert_called_once_with(aws_access_key_id='access_key_id',
                                        aws_secret_access_key='secret_access_key',
                                        profile_name='profile',
                                        region_name='region')
    mocked_client.assert_called_once_with('ecs')


@pytest.fixture
@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def client(mocked_init, mocked_client):
    mocked_init.return_value = None
    return EcsClient('access_key_id', 'secret_access_key', 'region', 'profile')


def test_client_describe_services(client):
    client.describe_services('my-cluster', 'my-service')
    client.boto.describe_services.assert_called_once_with(cluster='my-cluster', services=['my-service'])


def test_client_describe_task_definition(client):
    client.describe_task_definition('task_definition_arn')
    client.boto.describe_task_definition.assert_called_once_with(taskDefinition='task_definition_arn')


def test_client_list_tasks(client):
    client.list_tasks('my-cluster', 'my-service')
    client.boto.list_tasks.assert_called_once_with(cluster='my-cluster', serviceName='my-service')


def test_client_describe_tasks(client):
    client.describe_tasks('my-cluster', 'task-arns')
    client.boto.describe_tasks.assert_called_once_with(cluster='my-cluster', tasks='task-arns')


def test_client_register_task_definition(client):
    containers = [{'name': 'foo'}]
    volumes = [{'foo': 'bar'}]
    client.register_task_definition('family', containers, volumes)
    client.boto.register_task_definition.assert_called_once_with(family='family', containerDefinitions=containers,
                                                                 volumes=volumes)


def test_client_deregister_task_definition(client):
    client.deregister_task_definition('task_definition_arn')
    client.boto.deregister_task_definition.assert_called_once_with(taskDefinition='task_definition_arn')


def test_client_update_service(client):
    client.update_service('my-cluster', 'my-service', 5, 'task-definition')
    client.boto.update_service.assert_called_once_with(
        cluster='my-cluster',
        service='my-service',
        desiredCount=5,
        taskDefinition='task-definition'
    )
