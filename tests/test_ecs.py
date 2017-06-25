from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from boto3.session import Session
from botocore.exceptions import ClientError, NoCredentialsError
from dateutil.tz import tzlocal
from mock.mock import patch

from ecs_deploy.ecs import EcsService, EcsTaskDefinition, UnknownContainerError, EcsTaskDefinitionDiff, EcsClient, \
    EcsAction, ConnectionError, DeployAction, ScaleAction, RunAction

CLUSTER_NAME = u'test-cluster'
CLUSTER_ARN = u'arn:aws:ecs:eu-central-1:123456789012:cluster/%s' % CLUSTER_NAME
SERVICE_NAME = u'test-service'
SERVICE_ARN = u'ecs-svc/12345678901234567890'
DESIRED_COUNT = 2
TASK_DEFINITION_FAMILY_1 = u'test-task'
TASK_DEFINITION_REVISION_1 = 1
TASK_DEFINITION_ROLE_ARN_1 = u'arn:test:role:1'
TASK_DEFINITION_ARN_1 = u'arn:aws:ecs:eu-central-1:123456789012:task-definition/%s:%s' % (TASK_DEFINITION_FAMILY_1,
                                                                                          TASK_DEFINITION_REVISION_1)
TASK_DEFINITION_VOLUMES_1 = []
TASK_DEFINITION_CONTAINERS_1 = [
    {u'name': u'webserver', u'image': u'webserver:123', u'command': u'run',
     u'environment': ({"name": "foo", "value": "bar"}, {"name": "lorem", "value": "ipsum"})},
    {u'name': u'application', u'image': u'application:123', u'command': u'run'}
]
TASK_DEFINITION_FAMILY_2 = u'test-task'
TASK_DEFINITION_REVISION_2 = 2
TASK_DEFINITION_ARN_2 = u'arn:aws:ecs:eu-central-1:123456789012:task-definition/%s:%s' % (TASK_DEFINITION_FAMILY_2,
                                                                                          TASK_DEFINITION_REVISION_2)
TASK_DEFINITION_VOLUMES_2 = []
TASK_DEFINITION_CONTAINERS_2 = [
    {u'name': u'webserver', u'image': u'webserver:123', u'command': u'run',
     u'environment': ({"name": "foo", "value": "bar"}, {"name": "lorem", "value": "ipsum"})},
    {u'name': u'application', u'image': u'application:123', u'command': u'run'}
]

PAYLOAD_TASK_DEFINITION_1 = {
    u'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    u'family': TASK_DEFINITION_FAMILY_1,
    u'revision': TASK_DEFINITION_REVISION_1,
    u'taskRoleArn': TASK_DEFINITION_ROLE_ARN_1,
    u'volumes': deepcopy(TASK_DEFINITION_VOLUMES_1),
    u'containerDefinitions': deepcopy(TASK_DEFINITION_CONTAINERS_1),
}

PAYLOAD_TASK_DEFINITION_2 = {
    u'taskDefinitionArn': TASK_DEFINITION_ARN_2,
    u'family': TASK_DEFINITION_FAMILY_2,
    u'revision': TASK_DEFINITION_REVISION_2,
    u'volumes': deepcopy(TASK_DEFINITION_VOLUMES_2),
    u'taskRoleArn': '',
    u'containerDefinitions': deepcopy(TASK_DEFINITION_CONTAINERS_2),
}

TASK_ARN_1 = u'arn:aws:ecs:eu-central-1:123456789012:task/12345678-1234-1234-1234-123456789011'
TASK_ARN_2 = u'arn:aws:ecs:eu-central-1:123456789012:task/12345678-1234-1234-1234-123456789012'

PAYLOAD_TASK_1 = {
    u'taskArn': TASK_ARN_1,
    u'clusterArn': CLUSTER_ARN,
    u'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    u'containerInstanceArn': u'arn:aws:ecs:eu-central-1:123456789012:container-instance/12345678-123456-123456-123456',
    u'overrides': {u'containerOverrides': []},
    u'lastStatus': u'RUNNING',
    u'desiredStatus': u'RUNNING',
    u'containers': TASK_DEFINITION_CONTAINERS_1,
    u'startedBy': SERVICE_ARN
}

PAYLOAD_TASK_2 = {
    u'taskArn': TASK_ARN_2,
    u'clusterArn': CLUSTER_ARN,
    u'taskDefinitionArn': TASK_DEFINITION_ARN_1,
    u'containerInstanceArn': u'arn:aws:ecs:eu-central-1:123456789012:container-instance/12345678-123456-123456-123456',
    u'overrides': {u'containerOverrides': []},
    u'lastStatus': u'RUNNING',
    u'desiredStatus': u'RUNNING',
    u'containers': TASK_DEFINITION_CONTAINERS_1,
    u'startedBy': SERVICE_ARN
}

PAYLOAD_DEPLOYMENTS = [
    {
        u'status': u'PRIMARY',
        u'pendingCount': 0,
        u'desiredCount': DESIRED_COUNT,
        u'runningCount': DESIRED_COUNT,
        u'taskDefinition': TASK_DEFINITION_ARN_1,
        u'createdAt': datetime(2016, 3, 11, 12, 0, 0, 000000, tzinfo=tzlocal()),
        u'updatedAt': datetime(2016, 3, 11, 12, 5, 0, 000000, tzinfo=tzlocal()),
        u'id': u'ecs-svc/0000000000000000002',
    }
]

PAYLOAD_EVENTS = [
    {
        u'id': u'error',
        u'createdAt': datetime.now(tz=tzlocal()),
        u'message': u'Service was unable to Lorem Ipsum'
    },
    {
        u'id': u'older_error',
        u'createdAt': datetime(2016, 3, 11, 12, 0, 10, 000000, tzinfo=tzlocal()),
        u'message': u'Service was unable to Lorem Ipsum'
    }
]

PAYLOAD_SERVICE = {
    u'serviceName': SERVICE_NAME,
    u'desiredCount': DESIRED_COUNT,
    u'taskDefinition': TASK_DEFINITION_ARN_1,
    u'deployments': PAYLOAD_DEPLOYMENTS,
    u'events': []
}

PAYLOAD_SERVICE_WITH_ERRORS = {
    u'serviceName': SERVICE_NAME,
    u'desiredCount': DESIRED_COUNT,
    u'taskDefinition': TASK_DEFINITION_ARN_1,
    u'deployments': PAYLOAD_DEPLOYMENTS,
    u'events': PAYLOAD_EVENTS
}

PAYLOAD_SERVICE_WITHOUT_DEPLOYMENTS = {
    u'serviceName': SERVICE_NAME,
    u'desiredCount': DESIRED_COUNT,
    u'taskDefinition': TASK_DEFINITION_ARN_1,
    u'deployments': [],
    u'events': []
}

RESPONSE_SERVICE = {
    u"service": PAYLOAD_SERVICE
}

RESPONSE_SERVICE_WITH_ERRORS = {
    u"service": PAYLOAD_SERVICE_WITH_ERRORS
}

RESPONSE_DESCRIBE_SERVICES = {
    u"services": [PAYLOAD_SERVICE]
}

RESPONSE_TASK_DEFINITION = {
    u"taskDefinition": PAYLOAD_TASK_DEFINITION_1
}

RESPONSE_TASK_DEFINITION_2 = {
    u"taskDefinition": PAYLOAD_TASK_DEFINITION_2
}

RESPONSE_LIST_TASKS_2 = {
    u"taskArns": [TASK_ARN_1, TASK_ARN_2]
}

RESPONSE_LIST_TASKS_1 = {
    u"taskArns": [TASK_ARN_1]
}

RESPONSE_LIST_TASKS_0 = {
    u"taskArns": []
}

RESPONSE_DESCRIBE_TASKS = {
    u"tasks": [PAYLOAD_TASK_1, PAYLOAD_TASK_2]
}


@pytest.fixture()
def task_definition():
    return EcsTaskDefinition(deepcopy(PAYLOAD_TASK_DEFINITION_1))


@pytest.fixture
def task_definition_revision_2():
    return EcsTaskDefinition(deepcopy(PAYLOAD_TASK_DEFINITION_2))


@pytest.fixture
def service():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE))


@pytest.fixture
def service_with_errors():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITH_ERRORS))


@pytest.fixture
def service_without_deployments():
    return EcsService(CLUSTER_NAME, deepcopy(PAYLOAD_SERVICE_WITHOUT_DEPLOYMENTS))


def test_service_init(service):
    assert isinstance(service, dict)
    assert service.cluster == CLUSTER_NAME
    assert service[u'desiredCount'] == DESIRED_COUNT
    assert service[u'taskDefinition'] == TASK_DEFINITION_ARN_1


def test_service_set_desired_count(service):
    assert service.desired_count == DESIRED_COUNT
    service.set_desired_count(5)
    assert service.desired_count == 5


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
    assert u'webserver' in task_definition.container_names
    assert u'application' in task_definition.container_names
    assert u'foobar' not in task_definition.container_names


def test_task_volumes(task_definition):
    assert task_definition.volumes == TASK_DEFINITION_VOLUMES_2


def test_task_revision(task_definition):
    assert task_definition.revision == TASK_DEFINITION_REVISION_1


def test_task_no_diff(task_definition):
    assert task_definition.diff == []


def test_task_image_diff(task_definition):
    task_definition.set_images(u'foobar')
    assert len(task_definition.diff) == 2

    for diff in task_definition.diff:
        assert isinstance(diff, EcsTaskDefinitionDiff)


def test_task_set_tag(task_definition):
    task_definition.set_images(u'foobar')
    for container in task_definition.containers:
        assert container[u'image'].endswith(u':foobar')


def test_task_set_image(task_definition):
    task_definition.set_images(webserver=u'new-image:123', application=u'app-image:latest')
    for container in task_definition.containers:
        if container[u'name'] == u'webserver':
            assert container[u'image'] == u'new-image:123'
        if container[u'name'] == u'application':
            assert container[u'image'] == u'app-image:latest'


def test_task_set_environment(task_definition):
    task_definition.set_environment(((u'webserver', u'foo', u'baz'), (u'webserver', u'some-name', u'some-value')))

    assert {'name': 'lorem', 'value': 'ipsum'} in task_definition.containers[0]['environment']
    assert {'name': 'foo', 'value': 'baz'} in task_definition.containers[0]['environment']
    assert {'name': 'some-name', 'value': 'some-value'} in task_definition.containers[0]['environment']


def test_task_set_image_for_unknown_container(task_definition):
    with pytest.raises(UnknownContainerError):
        task_definition.set_images(foobar=u'new-image:123')


def test_task_set_command(task_definition):
    task_definition.set_commands(webserver=u'run-webserver', application=u'run-application')
    for container in task_definition.containers:
        if container[u'name'] == u'webserver':
            assert container[u'command'] == [u'run-webserver']
        if container[u'name'] == u'application':
            assert container[u'command'] == [u'run-application']


def test_task_set_command_for_unknown_container(task_definition):
    with pytest.raises(UnknownContainerError):
        task_definition.set_images(foobar=u'run-foobar')


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


def test_task_get_overrides_with_commandand_environment(task_definition):
    task_definition.set_commands(webserver='/usr/bin/python script.py')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 1
    assert overrides[0]['name'] == 'webserver'
    assert overrides[0]['command'] == ['/usr/bin/python','script.py']
    assert dict(name='foo', value='baz') in overrides[0]['environment']


def test_task_get_overrides_with_commandand_environment_for_multiple_containers(task_definition):
    task_definition.set_commands(application='/usr/bin/python script.py')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))
    overrides = task_definition.get_overrides()
    assert len(overrides) == 2
    assert overrides[0]['name'] == 'application'
    assert overrides[0]['command'] == ['/usr/bin/python','script.py']
    assert overrides[1]['name'] == 'webserver'
    assert dict(name='foo', value='baz') in overrides[1]['environment']


def test_task_get_overrides_command(task_definition):
    command = task_definition.get_overrides_command('/usr/bin/python script.py')
    assert isinstance(command, list)
    assert command == ['/usr/bin/python','script.py']


def test_task_get_overrides_environment(task_definition):
    environment = task_definition.get_overrides_environment(dict(foo='bar'))
    assert isinstance(environment, list)
    assert len(environment) == 1
    assert environment[0] == dict(name='foo', value='bar')


def test_task_definition_diff():
    diff = EcsTaskDefinitionDiff(u'webserver', u'image', u'new', u'old')
    assert str(diff) == u"Changed image of container 'webserver' to: \"new\" (was: \"old\")"


@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def test_client_init(mocked_init, mocked_client):
    mocked_init.return_value = None

    EcsClient(u'access_key_id', u'secret_access_key', u'region', u'profile')

    mocked_init.assert_called_once_with(aws_access_key_id=u'access_key_id',
                                        aws_secret_access_key=u'secret_access_key',
                                        profile_name=u'profile',
                                        region_name=u'region')
    mocked_client.assert_called_once_with(u'ecs')


@pytest.fixture
@patch.object(Session, 'client')
@patch.object(Session, '__init__')
def client(mocked_init, mocked_client):
    mocked_init.return_value = None
    return EcsClient(u'access_key_id', u'secret_access_key', u'region', u'profile')


def test_client_describe_services(client):
    client.describe_services(u'test-cluster', u'test-service')
    client.boto.describe_services.assert_called_once_with(cluster=u'test-cluster', services=[u'test-service'])


def test_client_describe_task_definition(client):
    client.describe_task_definition(u'task_definition_arn')
    client.boto.describe_task_definition.assert_called_once_with(taskDefinition=u'task_definition_arn')


def test_client_list_tasks(client):
    client.list_tasks(u'test-cluster', u'test-service')
    client.boto.list_tasks.assert_called_once_with(cluster=u'test-cluster', serviceName=u'test-service')


def test_client_describe_tasks(client):
    client.describe_tasks(u'test-cluster', u'task-arns')
    client.boto.describe_tasks.assert_called_once_with(cluster=u'test-cluster', tasks=u'task-arns')


def test_client_register_task_definition(client):
    containers = [{u'name': u'foo'}]
    volumes = [{u'foo': u'bar'}]
    role_arn = 'arn:test:role'
    client.register_task_definition(u'family', containers, volumes, role_arn)
    client.boto.register_task_definition.assert_called_once_with(
        family=u'family',
        containerDefinitions=containers,
        volumes=volumes,
        taskRoleArn=role_arn
    )


def test_client_deregister_task_definition(client):
    client.deregister_task_definition(u'task_definition_arn')
    client.boto.deregister_task_definition.assert_called_once_with(taskDefinition=u'task_definition_arn')


def test_client_update_service(client):
    client.update_service(u'test-cluster', u'test-service', 5, u'task-definition')
    client.boto.update_service.assert_called_once_with(
        cluster=u'test-cluster',
        service=u'test-service',
        desiredCount=5,
        taskDefinition=u'task-definition'
    )


def test_client_run_task(client):
    client.run_task(
        cluster=u'test-cluster',
        task_definition=u'test-task',
        count=2,
        started_by='test',
        overrides=dict(foo='bar')
    )

    client.boto.run_task.assert_called_once_with(
        cluster=u'test-cluster',
        taskDefinition=u'test-task',
        count=2,
        startedBy='test',
        overrides=dict(foo='bar')
    )


def test_ecs_action_init(client):
    action = EcsAction(client, u'test-cluster', u'test-service')
    assert action.client == client
    assert action.cluster_name == u'test-cluster'
    assert action.service_name == u'test-service'
    assert isinstance(action.service, EcsService)


def test_ecs_action_init_with_invalid_cluster():
    with pytest.raises(ConnectionError) as excinfo:
        client = EcsTestClient(u'access_key',  u'secret_key')
        EcsAction(client, u'invliad-cluster', u'test-service')
    assert str(excinfo.value) == u'An error occurred (ClusterNotFoundException) when calling the DescribeServices ' \
                                 u'operation: Cluster not found.'


def test_ecs_action_init_with_invalid_service():
    with pytest.raises(ConnectionError) as excinfo:
        client = EcsTestClient(u'access_key',  u'secret_key')
        EcsAction(client, u'test-cluster', u'invalid-service')
    assert str(excinfo.value) == u'An error occurred when calling the DescribeServices operation: Service not found.'


def test_ecs_action_init_without_credentials():
    with pytest.raises(ConnectionError) as excinfo:
        client = EcsTestClient()
        EcsAction(client, u'test-cluster', u'invalid-service')
    assert str(excinfo.value) == u'Unable to locate credentials. Configure credentials by running "aws configure".'


def test_ecs_action_get_service():
    client = EcsTestClient(u'access_key', u'secret_key')
    action = EcsAction(client, u'test-cluster', u'test-service')
    service = action.get_service()
    assert service.name == u'test-service'
    assert service.cluster == u'test-cluster'


@patch.object(EcsClient, '__init__')
def test_ecs_action_get_current_task_definition(client, service):
    client.describe_task_definition.return_value = RESPONSE_TASK_DEFINITION

    action = EcsAction(client, u'test-cluster', u'test-service')
    task_definition = action.get_current_task_definition(service)

    client.describe_task_definition.assert_called_once_with(service.task_definition)

    assert isinstance(task_definition, EcsTaskDefinition)
    assert task_definition.family == u'test-task'
    assert task_definition.revision == 1
    assert task_definition.arn == u'arn:aws:ecs:eu-central-1:123456789012:task-definition/test-task:1'


@patch.object(EcsClient, '__init__')
def test_update_task_definition(client, task_definition):
    client.register_task_definition.return_value = RESPONSE_TASK_DEFINITION

    action = EcsAction(client, u'test-cluster', u'test-service')
    new_task_definition = action.update_task_definition(task_definition)

    assert isinstance(new_task_definition, EcsTaskDefinition)
    client.register_task_definition.assert_called_once_with(
        task_definition.family,
        task_definition.containers,
        task_definition.volumes,
        task_definition.role_arn,
    )
    client.deregister_task_definition.assert_called_once_with(
        task_definition.arn
    )


@patch.object(EcsClient, '__init__')
def test_update_service(client, service):
    client.update_service.return_value = RESPONSE_SERVICE

    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    new_service = action.update_service(service)

    assert isinstance(new_service, EcsService)
    client.update_service.assert_called_once_with(service.cluster, service.name, service.desired_count,
                                                  service.task_definition)


@patch.object(EcsClient, '__init__')
def test_is_deployed(client, service):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_1
    client.describe_tasks.return_value = RESPONSE_DESCRIBE_TASKS

    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    is_deployed = action.is_deployed(service)

    assert is_deployed is True
    client.list_tasks.assert_called_once_with(service.cluster, service.name)


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
    service.set_desired_count(0)
    is_deployed = action.is_deployed(service)
    assert is_deployed is True


@patch.object(EcsClient, '__init__')
def test_is_not_deployed_if_no_tasks_running(client, service):
    client.list_tasks.return_value = RESPONSE_LIST_TASKS_0
    action = EcsAction(client, CLUSTER_NAME, SERVICE_NAME)
    is_deployed = action.is_deployed(service)
    assert is_deployed is False


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

    client.describe_services.assert_called_once_with(CLUSTER_NAME, SERVICE_NAME)
    client.update_service.assert_called_once_with(action.service.cluster, action.service.name,
                                                  action.service.desired_count, task_definition_revision_2.arn)


@patch.object(EcsClient, '__init__')
def test_scale_action(client):
    action = ScaleAction(client, CLUSTER_NAME, SERVICE_NAME)
    updated_service = action.scale(5)

    assert action.service.desired_count == 5
    assert isinstance(updated_service, EcsService)

    client.describe_services.assert_called_once_with(CLUSTER_NAME, SERVICE_NAME)
    client.update_service.assert_called_once_with(action.service.cluster, action.service.name,
                                                  5, action.service.task_definition)


@patch.object(EcsClient, '__init__')
def test_run_action(client):
    action = RunAction(client, CLUSTER_NAME)
    assert len(action.started_tasks) == 0


@patch.object(EcsClient, '__init__')
def test_run_action_run(client, task_definition):
    action = RunAction(client, CLUSTER_NAME)
    client.run_task.return_value = dict(tasks=[dict(taskArn='A'), dict(taskArn='B')])
    action.run(task_definition, 2, 'test')

    client.run_task.assert_called_once_with(
        cluster=CLUSTER_NAME,
        task_definition=task_definition.family_revision,
        count=2,
        started_by='test',
        overrides=dict(containerOverrides=task_definition.get_overrides())
    )

    assert len(action.started_tasks) == 2


class EcsTestClient(object):
    def __init__(self, access_key_id=None, secret_access_key=None, region=None, profile=None, errors=False, wait=0):
        super(EcsTestClient, self).__init__()
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.profile = profile
        self.errors = errors
        self.wait_until = datetime.now() + timedelta(seconds=wait)

    def describe_services(self, cluster_name, service_name):
        if not self.access_key_id or not self.secret_access_key:
            raise NoCredentialsError()
        if cluster_name != u'test-cluster':
            error_response = {u'Error': {u'Code': u'ClusterNotFoundException', u'Message': u'Cluster not found.'}}
            raise ClientError(error_response, u'DescribeServices')
        if service_name != u'test-service':
            return {u'services': []}
        if self.errors:
            return {
                u"services": [PAYLOAD_SERVICE_WITH_ERRORS],
                u"failures": []
            }
        return {
            u"services": [PAYLOAD_SERVICE],
            u"failures": []
        }

    def describe_task_definition(self, task_definition_arn):
        return deepcopy(RESPONSE_TASK_DEFINITION)

    def list_tasks(self, cluster_name, service_name):
        if self.wait_until <= datetime.now():
            return deepcopy(RESPONSE_LIST_TASKS_2)
        return deepcopy(RESPONSE_LIST_TASKS_0)

    def describe_tasks(self, cluster_name, task_arns):
        return deepcopy(RESPONSE_DESCRIBE_TASKS)

    def register_task_definition(self, family, containers, volumes, role_arn):
        return deepcopy(RESPONSE_TASK_DEFINITION_2)

    def deregister_task_definition(self, task_definition_arn):
        return deepcopy(RESPONSE_TASK_DEFINITION)

    def update_service(self, cluster, service, desired_count, task_definition):
        if self.errors:
            return deepcopy(RESPONSE_SERVICE_WITH_ERRORS)
        return deepcopy(RESPONSE_SERVICE)

    def run_task(self, cluster, task_definition, count, started_by, overrides):
        if not self.access_key_id or not self.secret_access_key:
            raise ConnectionError(u'Unable to locate credentials. Configure credentials by running "aws configure".')
        if cluster == 'unknown-cluster':
            raise ConnectionError(u'An error occurred (ClusterNotFoundException) when calling the RunTask operation: Cluster not found.')
        if self.errors:
            error = dict(Error=dict(Code=123, Message="Something went wrong"))
            raise ClientError(error, 'fake_error')
        return dict(tasks=[dict(taskArn='arn:foo:bar'), dict(taskArn='arn:lorem:ipsum')])
