from __future__ import print_function, absolute_import

from os import getenv
from time import sleep

import click
import getpass
from datetime import datetime, timedelta

from ecs_deploy.ecs import DeployAction, ScaleAction, RunAction, EcsClient
from ecs_deploy.newrelic import Deployment, NewRelicDeploymentException


@click.group()
def ecs(): # pragma: no cover
    pass


def get_client(access_key_id, secret_access_key, region, profile):
    return EcsClient(access_key_id, secret_access_key, region, profile)


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.option('-t', '--tag', help='Changes the tag for ALL container images')
@click.option('-i', '--image', type=(str, str), multiple=True, help='Overwrites the image for a container: <container> <image>')
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('-r', '--role', type=str, help='Sets the task\'s role ARN: <task role ARN>')
@click.option('--region', required=False, help='AWS region')
@click.option('--access-key-id', required=False, help='AWS access key id')
@click.option('--secret-access-key', required=False, help='AWS secret access yey')
@click.option('--profile', required=False, help='AWS configuration profile')
@click.option('--timeout', required=False, default=300, type=int, help='Amount of seconds to wait for deployment before command fails (default: 300)')
@click.option('--newrelic-apikey', required=False, help='New Relic API Key for recording the deployment')
@click.option('--newrelic-appid', required=False, help='New Relic App ID for recording the deployment')
@click.option('--comment', required=False, help='Description/comment for recording the deployment')
@click.option('--user', required=False, help='User who executes the deployment (used for recording)')
def deploy(cluster, service, tag, image, command, env, role, access_key_id, secret_access_key, region, profile, timeout,
           newrelic_apikey, newrelic_appid, comment, user):
    """
    Redeploy or modify a service.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.

    When not giving any other options, the task definition will not be changed. It will just be duplicated, so that
    all container images will be pulled and redeployed.
    """

    try:
        client = get_client(access_key_id, secret_access_key, region, profile)
        deployment = DeployAction(client, cluster, service)
        task_definition = deployment.get_current_task_definition(deployment.service)

        task_definition.set_images(tag, **{key: value for (key, value) in image})
        task_definition.set_commands(**{key: value for (key, value) in command})
        task_definition.set_environment(env)
        task_definition.set_role_arn(role)
        print_diff(task_definition)

        click.secho('Creating new task definition revision')
        new_task_definition = deployment.update_task_definition(task_definition)
        click.secho('Successfully created revision: %d' % new_task_definition.revision, fg='green')
        click.secho('Successfully deregistered revision: %d\n' % task_definition.revision, fg='green')

        record_deployment(tag, newrelic_apikey, newrelic_appid, comment, user)

        click.secho('Updating service')
        deployment.deploy(new_task_definition)
        click.secho('Successfully changed task definition to: %s:%s\n' %
                    (new_task_definition.family, new_task_definition.revision), fg='green')

        wait_for_finish(deployment, timeout, 'Deploying task definition', 'Deployment successful', 'Deployment failed')

    except Exception as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.argument('desired_count', type=int)
@click.option('--region', help='AWS region')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access yey')
@click.option('--profile', help='AWS configuration profile')
@click.option('--timeout', default=300, type=int, help='AWS configuration profile')
def scale(cluster, service, desired_count, access_key_id, secret_access_key, region, profile, timeout):
    """
    Scale a service up or down.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.
    DESIRED_COUNT is the number of tasks your service should run.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile)
        scaling = ScaleAction(client, cluster, service)
        click.secho('Updating service')
        scaling.scale(desired_count)
        click.secho('Successfully changed desired count to: %s\n' % desired_count, fg='green')
        wait_for_finish(scaling, timeout, 'Scaling service', 'Scaling successful', 'Scaling failed')

    except Exception as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('task')
@click.argument('count', required=False, default=1)
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('--region', help='AWS region')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access yey')
@click.option('--profile', help='AWS configuration profile')
def run(cluster, task, count, command, env, region, access_key_id, secret_access_key, profile):
    """
    Run a one-off task.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    TASK is the name of your task definintion (e.g. 'mytask') within ECS.
    COMMAND is the number of tasks your service should run.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile)
        action = RunAction(client, cluster)

        task_definition = action.get_task_definition(task)
        task_definition.set_commands(**{key: value for (key, value) in command})
        task_definition.set_environment(env)
        print_diff(task_definition, 'Using task definition: %s' % task)

        action.run(task_definition, count, 'ECS Deploy')

        click.secho('Successfully started %d instances of task: %s' % (len(action.started_tasks), task_definition.family_revision), fg='green')
        for started_task in action.started_tasks:
            click.secho('- %s' % started_task['taskArn'], fg='green')
        click.secho(' ')

    except Exception as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


def wait_for_finish(action, timeout, title, success_message, failure_message):
    click.secho(title, nl=False)
    waiting = True
    waiting_timeout = datetime.now() + timedelta(seconds=timeout)
    while waiting and datetime.now() < waiting_timeout:
        sleep(1)
        click.secho('.', nl=False)
        service = action.get_service()
        waiting = not action.is_deployed(service) and not service.errors

    if waiting or service.errors:
        print_errors(service, waiting, failure_message)
        exit(1)

    click.secho('\n%s\n' % success_message, fg='green')
    exit(0)


def record_deployment(revision, newrelic_apikey, newrelic_appid, comment, user):
    newrelic_apikey = getenv('NEW_RELIC_API_KEY', newrelic_apikey)
    newrelic_appid = getenv('NEW_RELIC_APP_ID', newrelic_appid)

    if not revision or not newrelic_apikey or not newrelic_appid:
        return False

    user = user or getpass.getuser()

    click.secho('Recording deployment in New Relic', nl=False)

    deployment = Deployment(newrelic_apikey, newrelic_appid, user)
    deployment.deploy(revision, '', comment)

    click.secho('\nDone\n', fg='green')

    return True


def print_diff(task_definition, title='Updating task definition'):
    if task_definition.diff:
        click.secho(title)
        for diff in task_definition.diff:
            click.secho(str(diff), fg='blue')
        click.secho('')


def print_errors(service, was_timeout=False, message=''):
    if was_timeout:
        click.secho('\n%s (timeout)\n' % message, fg='red', err=True)
    else:
        click.secho('\n%s\n' % message, fg='red', err=True)

    for timestamp in service.errors:
        click.secho('%s\n%s\n' % (timestamp, service.errors[timestamp]), fg='red', err=True)

    if service.older_errors:
        click.secho('Older errors', fg='yellow', err=True)
        for timestamp in service.older_errors:
            click.secho('%s\n%s\n' % (timestamp, service.older_errors[timestamp]), fg='yellow', err=True)


ecs.add_command(deploy)
ecs.add_command(scale)
ecs.add_command(run)

if __name__ == '__main__':  # pragma: no cover
    ecs()
