import pytest
from click.testing import CliRunner
from mock.mock import patch

from ecs_deploy import cli
from ecs_deploy.cli import get_client
from ecs_deploy.ecs import EcsClient
from tests.test_ecs import EcsTestClient, CLUSTER_NAME, SERVICE_NAME


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
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" not in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_new_tag(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Updating task definition" in result.output
    assert u"Changed image of container 'webserver' to: webserver:latest (was: webserver:123)" in result.output
    assert u"Changed image of container 'application' to: application:latest (was: application:123)" in result.output
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
    assert u"Updating task definition" in result.output
    assert u"Changed image of container 'application' to: application:latest (was: application:123)" in result.output
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
    assert u"Updating task definition" in result.output
    assert u"Changed image of container 'webserver' to: webserver:latest (was: webserver:123)" in result.output
    assert u"Changed image of container 'application' to: application:latest (was: application:123)" in result.output
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
    assert u"Updating task definition" in result.output
    assert u"Changed command of container 'application' to: foobar (was: run)" in result.output
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_with_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', errors=True)
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME))
    assert result.exit_code == 1
    assert u"Deployment failed" in result.output
    assert u"ERROR: Service was unable to Lorem Ipsum" in result.output


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
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', errors=True)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2'))
    assert result.exit_code == 1
    assert u"Scaling failed" in result.output
    assert u"ERROR: Service was unable to Lorem Ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_scale_with_timeout(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', wait=2)
    result = runner.invoke(cli.scale, (CLUSTER_NAME, SERVICE_NAME, '2', '--timeout', '1'))
    assert result.exit_code == 1
    assert u"Scaling failed (timeout)" in result.output
