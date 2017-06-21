import pytest
from click.testing import CliRunner
from mock.mock import patch

from ecs_deploy import cli
from ecs_deploy.cli import get_client, record_deployment
from ecs_deploy.ecs import EcsClient
from ecs_deploy.newrelic import Deployment, NewRelicDeploymentException
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
def test_deploy_with_role_arn(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-r', 'arn:new:role'))
    assert result.exit_code == 0
    assert not result.exception
    assert u'Successfully created revision: 2' in result.output
    assert u'Successfully deregistered revision: 1' in result.output
    assert u'Successfully changed task definition to: test-task:2' in result.output
    assert u'Deployment successful' in result.output
    assert u"Updating task definition" in result.output
    assert u"Changed role_arn to: \"arn:new:role\" (was: \"arn:test:role:1\")" in result.output


@patch('ecs_deploy.cli.get_client')
def test_deploy_new_tag(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.deploy, (CLUSTER_NAME, SERVICE_NAME, '-t', 'latest'))
    assert result.exit_code == 0
    assert not result.exception
    assert u"Updating task definition" in result.output
    assert u"Changed image of container 'webserver' to: \"webserver:latest\" (was: \"webserver:123\")" in result.output
    assert u"Changed image of container 'application' to: \"application:latest\" (was: \"application:123\")" in result.output
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
    assert u"Changed image of container 'application' to: \"application:latest\" (was: \"application:123\")" in result.output
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
    assert u"Changed image of container 'webserver' to: \"webserver:latest\" (was: \"webserver:123\")" in result.output
    assert u"Changed image of container 'application' to: \"application:latest\" (was: \"application:123\")" in result.output
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
    assert u"Changed command of container 'application' to: \"foobar\" (was: \"run\")" in result.output
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

    assert u"Updating task definition" in result.output
    assert u'Changed environment of container \'application\' to: {"foo": "bar"} (was: {})' in result.output
    assert u'Changed environment of container \'webserver\' to: ' in result.output
    assert u'"foo": "baz"' in result.output
    assert u'"lorem": "ipsum"' in result.output
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

    assert u"Successfully started 2 instances of task: test-task:1" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_command(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task', '2', '-c', 'webserver', 'date'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Using task definition: test-task" in result.output
    assert u"Changed command of container 'webserver' to: \"date\" (was: \"run\")" in result.output
    assert u"Successfully started 2 instances of task: test-task:1" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_environment_var(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key')
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task', '2', '-e', 'application', 'foo', 'bar'))

    assert not result.exception
    assert result.exit_code == 0

    assert u"Using task definition: test-task" in result.output
    assert u'Changed environment of container \'application\' to: {"foo": "bar"} (was: {})' in result.output
    assert u"Successfully started 2 instances of task: test-task:1" in result.output
    assert u"- arn:foo:bar" in result.output
    assert u"- arn:lorem:ipsum" in result.output


@patch('ecs_deploy.cli.get_client')
def test_run_task_with_errors(get_client, runner):
    get_client.return_value = EcsTestClient('acces_key', 'secret_key', errors=True)
    result = runner.invoke(cli.run, (CLUSTER_NAME, 'test-task'))
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
