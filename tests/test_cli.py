from datetime import datetime

import pytest
from click.testing import CliRunner
from mock.mock import patch

from ecs_deploy import cli
from ecs_deploy.cli import get_client, record_deployment
from ecs_deploy.ecs import EcsClient
from ecs_deploy.newrelic import Deployment, NewRelicDeploymentException
from tests.test_ecs import EcsTestClient, CLUSTER_NAME, SERVICE_NAME, \
    TASK_DEFINITION_ARN_1, TASK_DEFINITION_ARN_2


@pytest.fixture
def runner():
    return CliRunner()


@patch.object(EcsClient, '__init__')
def test_get_client(ecs_client):
    ecs_client.return_value = None
    client = get_client('access_key_id', 'secret_access_key', 'region', 'profile')
    ecs_client.assert_called_once_with('access_key_id', 'secret_access_key', 'region', 'profile')
    assert isinstance(client, EcsClient)


def test_ecs(runner):
    result = runner.invoke(cli.ecs)
    assert result.exit_code == 0
    assert not result.exception
    assert 'Usage: ecs [OPTIONS] COMMAND [ARGS]' in result.output
    assert '  deploy  ' in result.output
    assert '  scale   ' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_without_credentials(get_client, runner):
    get_client.return_value = EcsTestClient()
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 1
    assert result.output == u'Unable to locate credentials. Configure credentials by running "aws configure".\n\n'


@patch('ecs_deploy.cli.get_client')
def test_update_task_with_invalid_cluster(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, ('unknown-cluster', SERVICE_NAME))
    assert result.exit_code == 1
    assert result.output == u'An error occurred (ClusterNotFoundException) when calling the DescribeServices ' \
                            u'operation: Cluster not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_update_task_with_invalid_service(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, 'unknown-service'))
    assert result.exit_code == 1
    assert result.output == u'An error occurred when calling the DescribeServices operation: Service not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_update_task(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_with_role_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-r', 'arn:new:role'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed role_arn to: "arn:new:role" (was: "arn:test:role:1")' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_new_tag(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "webserver" to: "webserver:latest" (was: "webserver:123")' in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_one_new_image(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-i', 'application', 'application:latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_two_new_images(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-i', 'application', 'application:latest',
                                        '-i', 'webserver', 'webserver:latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "webserver" to: "webserver:latest" (was: "webserver:123")' in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_one_new_command(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-c', 'application', 'foobar'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed command of container "application" to: "foobar" (was: "run")' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_one_new_environment_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME,
                                        '-e', 'application', 'foo', 'bar',
                                        '-e', 'webserver', 'foo', 'baz'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "foo" of container "application" to: "bar"' in result.output
    assert u'Changed environment "foo" of container "webserver" to: "baz"' in result.output
    assert u'Changed environment "lorem" of container "webserver" to: "ipsum"' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_change_environment_variable_empty_string(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'application', 'foo', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "foo" of container "application" to: ""' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_new_empty_environment_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'application', 'new', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "new" of container "application" to: ""' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_empty_environment_variable_again(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'empty', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_previously_empty_environment_variable_with_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'empty', 'not-empty'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "empty" of container "webserver" to: "not-empty"' in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_exclusive_environment(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'new-env', 'new-value', '--exclusive-env'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "new-env" of container "webserver" to: "new-value"' in result.output

    assert u'Removed environment "foo" of container "webserver"' in result.output
    assert u'Removed environment "lorem" of container "webserver"' in result.output

    assert u'Removed secret' not in result.output

    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_exclusive_secret(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-s', 'webserver', 'new-secret', 'new-place', '--exclusive-secrets'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed secret "new-secret" of container "webserver" to: "new-place"' in result.output

    assert u'Removed secret "baz" of container "webserver"' in result.output
    assert u'Removed secret "dolor" of container "webserver"' in result.output

    assert u'Removed environment' not in result.output

    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_one_new_secret_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME,
                                        '-s', 'application', 'baz', 'qux',
                                        '-s', 'webserver', 'baz', 'quux'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed secret "baz" of container "application" to: "qux"' in result.output
    assert u'Changed secret "baz" of container "webserver" to: "quux"' in result.output
    assert u'Changed secret "dolor" of container "webserver" to: "sit"' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_without_changing_environment_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'foo', 'bar'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_without_changing_secrets_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-s', 'webserver', 'baz', 'qux'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed secrets' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_without_diff(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest', '-e', 'webserver', 'foo', 'barz', '--no-diff'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Update task based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_task_definition_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.update_task, (CLUSTER_NAME, SERVICE_NAME, '--task', TASK_DEFINITION_ARN_2))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Update task based on task definition: test-task:2" in result.output


@patch('ecs_deploy.cli.get_client')
def test_update_task_unknown_task_definition_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--task', u'arn:aws:ecs:eu-central-1:123456789012:task-definition/foobar:55'))
    assert result.exit_code == 1
    assert u"Unknown task definition arn: arn:aws:ecs:eu-central-1:123456789012:task-definition/foobar:55" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_credentials(get_client, runner):
    get_client.return_value = EcsTestClient()
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 1
    assert result.output == u'Unable to locate credentials. Configure credentials by running "aws configure".\n\n'


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_invalid_cluster(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, ('unknown-cluster', SERVICE_NAME))
    assert result.exit_code == 1
    assert result.output == u'An error occurred (ClusterNotFoundException) when calling the DescribeServices ' \
                            u'operation: Cluster not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_invalid_service(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, 'unknown-service'))
    assert result.exit_code == 1
    assert result.output == u'An error occurred when calling the DescribeServices operation: Service not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_deploy(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" not in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_rollback(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--timeout=1', '--rollback'))

    assert result.exit_code == 1
    assert result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output

    assert u"Deployment failed" in result.output
    assert u"Rolling back to task definition: test-task:1" in result.output
    assert u'Successfully changed task definition to: test-task:1' in result.output

    assert u"Rollback successful" in result.output
    assert u'Deployment failed, but service has been rolled back to ' \
           u'previous task definition: test-task:1' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_deregister(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--no-deregister'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' not in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" not in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_role_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-r', 'arn:new:role'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed role_arn to: "arn:new:role" (was: "arn:test:role:1")' in result.output

@patch('ecs_deploy.cli.get_client')
def test_deploy_with_execution_role_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-x', 'arn:new:role'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed execution_role_arn to: "arn:new:role" (was: "arn:test:role:1")' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_new_tag(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "webserver" to: "webserver:latest" (was: "webserver:123")' in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_one_new_image(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-i', 'application', 'application:latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_two_new_images(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-i', 'application', 'application:latest',
                                        '-i', 'webserver', 'webserver:latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed image of container "webserver" to: "webserver:latest" (was: "webserver:123")' in result.output
    assert u'Changed image of container "application" to: "application:latest" (was: "application:123")' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_one_new_command(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-c', 'application', 'foobar'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed command of container "application" to: "foobar" (was: "run")' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_one_new_environment_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME,
                                        '-e', 'application', 'foo', 'bar',
                                        '-e', 'webserver', 'foo', 'baz'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "foo" of container "application" to: "bar"' in result.output
    assert u'Changed environment "foo" of container "webserver" to: "baz"' in result.output
    assert u'Changed environment "lorem" of container "webserver" to: "ipsum"' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_change_environment_variable_empty_string(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'application', 'foo', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "foo" of container "application" to: ""' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_new_empty_environment_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'application', 'new', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "new" of container "application" to: ""' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_empty_environment_variable_again(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'empty', ''))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_previously_empty_environment_variable_with_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'empty', 'not-empty'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "empty" of container "webserver" to: "not-empty"' in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_exclusive_environment(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'new-env', 'new-value', '--exclusive-env'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed environment "new-env" of container "webserver" to: "new-value"' in result.output

    assert u'Removed environment "foo" of container "webserver"' in result.output
    assert u'Removed environment "lorem" of container "webserver"' in result.output

    assert u'Removed secret' not in result.output

    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_exclusive_secret(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-s', 'webserver', 'new-secret', 'new-place', '--exclusive-secrets'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed secret "new-secret" of container "webserver" to: "new-place"' in result.output

    assert u'Removed secret "baz" of container "webserver"' in result.output
    assert u'Removed secret "dolor" of container "webserver"' in result.output

    assert u'Removed environment' not in result.output

    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_one_new_secret_variable(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME,
                                        '-s', 'application', 'baz', 'qux',
                                        '-s', 'webserver', 'baz', 'quux'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" in result.output
    assert u'Changed secret "baz" of container "application" to: "qux"' in result.output
    assert u'Changed secret "baz" of container "webserver" to: "quux"' in result.output
    assert u'Changed secret "dolor" of container "webserver" to: "sit"' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_changing_environment_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-e', 'webserver', 'foo', 'bar'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_changing_secrets_value(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-s', 'webserver', 'baz', 'qux'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed secrets' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_diff(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest', '-e', 'webserver', 'foo', 'barz', '--no-diff'))

    assert result.exit_code == 0
    assert not result.exception

    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u"Updating task definition" not in result.output
    assert u'Changed environment' not in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', deployment_errors=True)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 1
    assert u"Deployment failed" in result.output
    assert u"ERROR: Service was unable to Lorem Ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_client_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', client_errors=True)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 1
    assert u"Something went wrong" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_ignore_warnings(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', deployment_errors=True)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--ignore-warnings'))

    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u"WARNING: Service was unable to Lorem Ipsum" in result.output
    assert u"Continuing." in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.newrelic.Deployment.deploy')
@patch('ecs_deploy.cli.get_client')
def test_deploy_with_newrelic(get_client, newrelic, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME,
                                        '-t', 'my-tag',
                                        '--newrelic-apikey', 'test',
                                        '--newrelic-appid', 'test',
                                        '--comment', 'Lorem Ipsum'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:1" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Recording deployment in New Relic" in result.output

    newrelic.assert_called_once_with(
        'my-tag',
        '',
        'Lorem Ipsum'
    )


@patch('ecs_deploy.newrelic.Deployment.deploy')
@patch('ecs_deploy.cli.get_client')
def test_deploy_with_newrelic_errors(get_client, deploy, runner):
    e = NewRelicDeploymentException('Recording deployment failed')
    deploy.side_effect = e

    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME,
                                        '-t', 'test',
                                        '--newrelic-apikey', 'test',
                                        '--newrelic-appid', 'test'))

    assert result.exit_code == 1
    assert u"Recording deployment failed" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_task_definition_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--task', TASK_DEFINITION_ARN_2))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Deploying based on task definition: test-task:2" in result.output
    assert u'Successfully deregistered revision: 2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_timeout(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--timeout', '1'))
    assert result.exit_code == 1
    assert u"Deployment failed due to timeout. Please see: " \
           u"https://github.com/fabfuel/ecs-deploy#timeout" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_wait_within_timeout(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--timeout', '10'))
    assert result.exit_code == 0
    assert u'Deploying new task definition...' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_without_timeout(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)

    start_time = datetime.now()
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--timeout', '-1'))
    end_time = datetime.now()

    assert result.exit_code == 0

    # assert task is not waiting for deployment
    assert u'Deploying new task definition\n' in result.output
    assert u'...' not in result.output
    assert (end_time - start_time).total_seconds() < 1


@patch('ecs_deploy.cli.get_client')
def test_deploy_unknown_task_definition_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '--task', u'arn:aws:ecs:eu-central-1:123456789012:task-definition/foobar:55'))
    assert result.exit_code == 1
    assert u"Unknown task definition arn: arn:aws:ecs:eu-central-1:123456789012:task-definition/foobar:55" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_without_credentials(get_client, runner):
    get_client.return_value = EcsTestClient()
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert result.output == u'Unable to locate credentials. Configure credentials by running "aws configure".\n\n'


@patch('ecs_deploy.cli.get_client')
def test_scale_with_invalid_cluster(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.scale, ('unknown-cluster', SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert result.output == u'An error occurred (ClusterNotFoundException) when calling the DescribeServices ' \
                            u'operation: Cluster not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_scale_with_invalid_service(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.scale, (CLUSTER_NAME, 'unknown-service', '2'))
    assert result.exit_code == 1
    assert result.output == u'An error occurred when calling the DescribeServices operation: Service not found.\n\n'


@patch('ecs_deploy.cli.get_client')
def test_scale(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert not result.exception
    assert result.exit_code == 0
    assert u"Successfully changed desired count to: 2" in result.output
    assert u"Scaling successful" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_with_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', deployment_errors=True)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert u"Scaling failed" in result.output
    assert u"ERROR: Service was unable to Lorem Ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_with_client_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', client_errors=True)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert u"Something went wrong" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_ignore_warnings(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', deployment_errors=True)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2', '--ignore-warnings'))

    assert not result.exception
    assert result.exit_code == 0
    assert u"Successfully changed desired count to: 2" in result.output
    assert u"WARNING: Service was unable to Lorem Ipsum" in result.output
    assert u"Continuing." in result.output
    assert u"Scaling successful" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_with_timeout(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2', '--timeout', '1'))
    assert result.exit_code == 1
    assert u"Scaling failed due to timeout. Please see: " \
           u"https://github.com/fabfuel/ecs-deploy#timeout" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_without_credentials(get_client, runner):
    get_client.return_value = EcsTestClient()
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert result.output == u'Unable to locate credentials. Configure credentials by running "aws configure".\n\n'


@patch('ecs_deploy.cli.get_client')
def test_run_task(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Successfully started 2 instances of task: test-task:2" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_command(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task', '2', '-c', 'webserver', 'date'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Using task definition: test-task" in result.output
    assert u'Changed command of container "webserver" to: "date" (was: "run")' in result.output
    assert u"Successfully started 2 instances of task: test-task:2" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_environment_var(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task', '2', '-e', 'application', 'foo', 'bar'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Using task definition: test-task" in result.output
    assert u'Changed environment "foo" of container "application" to: "bar"' in result.output
    assert u"Successfully started 2 instances of task: test-task:2" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_without_diff(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task', '2', '-e', 'application', 'foo', 'bar', '--no-diff'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Using task definition: test-task" not in result.output
    assert u'Changed environment' not in result.output
    assert u"Successfully started 2 instances of task: test-task:2" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', deployment_errors=True)
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task'))
    assert result.exception
    assert result.exit_code == 1
    assert u"An error occurred (123) when calling the fake_error operation: Something went wrong" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_without_credentials(get_client, runner):
    get_client.return_value = EcsTestClient()
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task'))
    assert result.exit_code == 1
    assert result.output == u'Unable to locate credentials. Configure credentials by running "aws configure".\n\n'


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_invalid_cluster(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, ('unknown-cluster', 'test-task'))
    assert result.exit_code == 1
    assert result.output == u'An error occurred (ClusterNotFoundException) when calling the RunTask operation: Cluster not found.\n\n'


@patch('ecs_deploy.newrelic.Deployment')
def test_record_deployment_without_revision(Deployment):
    result = record_deployment(None, None, None, None, None)
    assert result is False


@patch('ecs_deploy.newrelic.Deployment')
def test_record_deployment_without_apikey(Deployment):
    result = record_deployment('1.2.3', None, None, None, None)
    assert result is False


@patch('ecs_deploy.newrelic.Deployment')
def test_record_deployment_without_appid(Deployment):
    result = record_deployment('1.2.3', 'APIKEY', None, None, None)
    assert result is False


@patch('click.secho')
@patch.object(Deployment, 'deploy')
@patch.object(Deployment, '__init__')
def test_record_deployment(deployment_init, deployment_deploy, secho):
    deployment_init.return_value = None
    result = record_deployment('1.2.3', 'APIKEY', 'APPID', 'Comment', 'user')

    deployment_init.assert_called_once_with('APIKEY', 'APPID', 'user')
    deployment_deploy.assert_called_once_with('1.2.3', '', 'Comment')
    secho.assert_any_call('Recording deployment in New Relic', nl=False)
    secho.assert_any_call('\nDone\n', fg='green')

    assert result is True
