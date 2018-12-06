from __future__ import print_function, absolute_import

from os import getenv
from time import sleep

import click
import getpass
from datetime import datetime, timedelta

from ecs_deploy import VERSION
from ecs_deploy.ecs import DeployAction, ScaleAction, RunAction, EcsClient, \
    TaskPlacementError, EcsError
from ecs_deploy.newrelic import Deployment, NewRelicException


@click.group()
@click.version_option(version=VERSION, prog_name='ecs-deploy')
def ecs():  # pragma: no cover
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
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('-r', '--role', type=str, help='Sets the task\'s role ARN: <task role ARN>')
@click.option('--task', type=str, help='Task definition to be deployed. Can be a task ARN or a task family with optional revision')
@click.option('--region', required=False, help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', required=False, help='AWS access key id')
@click.option('--secret-access-key', required=False, help='AWS secret access key')
@click.option('--profile', required=False, help='AWS configuration profile name')
@click.option('--timeout', required=False, default=300, type=int, help='Amount of seconds to wait for deployment before command fails (default: 300)')
@click.option('--ignore-warnings', is_flag=True, help='Do not fail deployment on warnings (port already in use or insufficient memory/CPU)')
@click.option('--newrelic-apikey', required=False, help='New Relic API Key for recording the deployment')
@click.option('--newrelic-appid', required=False, help='New Relic App ID for recording the deployment')
@click.option('--comment', required=False, help='Description/comment for recording the deployment')
@click.option('--user', required=False, help='User who executes the deployment (used for recording)')
@click.option('--diff/--no-diff', default=True, help='Print which values were changed in the task definition (default: --diff)')
@click.option('--deregister/--no-deregister', default=True, help='Deregister or keep the old task definition (default: --deregister)')
@click.option('--rollback/--no-rollback', default=False, help='Rollback to previous revision, if deployment failed (default: --no-rollback)')
def deploy(cluster, service, tag, image, command, env, secret, role, task, region, access_key_id, secret_access_key, profile, timeout, newrelic_apikey, newrelic_appid, comment, user, ignore_warnings, diff, deregister, rollback):
    """
    Redeploy or modify a service.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.

    When not giving any other options, the task definition will not be changed.
    It will just be duplicated, so that all container images will be pulled
    and redeployed.
    """

    try:
        client = get_client(access_key_id, secret_access_key, region, profile)
        deployment = DeployAction(client, cluster, service)

        td = get_task_definition(deployment, task)
        td.set_images(tag, **{key: value for (key, value) in image})
        td.set_commands(**{key: value for (key, value) in command})
        td.set_environment(env)
        td.set_secrets(secret)
        td.set_role_arn(role)

        if diff:
            print_diff(td)

        new_td = create_task_definition(deployment, td)

        try:
            deploy_task_definition(
                deployment=deployment,
                task_definition=new_td,
                title='Deploying new task definition',
                success_message='Deployment successful',
                failure_message='Deployment failed',
                timeout=timeout,
                deregister=deregister,
                previous_task_definition=td,
                ignore_warnings=ignore_warnings,
            )

        except TaskPlacementError as e:
            if rollback:
                click.secho('%s\n' % str(e), fg='red', err=True)
                rollback_task_definition(deployment, td, new_td)
                exit(1)
            else:
                raise

        record_deployment(tag, newrelic_apikey, newrelic_appid, comment, user)

    except (EcsError, NewRelicException) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.argument('desired_count', type=int)
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--timeout', default=300, type=int, help='AWS configuration profile')
@click.option('--ignore-warnings', is_flag=True, help='Do not fail deployment on warnings (port already in use or insufficient memory/CPU)')
def scale(cluster, service, desired_count, access_key_id, secret_access_key, region, profile, timeout, ignore_warnings):
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
        click.secho(
            'Successfully changed desired count to: %s\n' % desired_count,
            fg='green'
        )
        wait_for_finish(
            action=scaling,
            timeout=timeout,
            title='Scaling service',
            success_message='Scaling successful',
            failure_message='Scaling failed',
            ignore_warnings=ignore_warnings
        )

    except EcsError as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('task')
@click.argument('count', required=False, default=1)
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--diff/--no-diff', default=True, help='Print what values were changed in the task definition')
def run(cluster, task, count, command, env, secret, region, access_key_id, secret_access_key, profile, diff):
    """
    Run a one-off task.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    TASK is the name of your task definition (e.g. 'my-task') within ECS.
    COMMAND is the number of tasks your service should run.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile)
        action = RunAction(client, cluster)

        td = action.get_task_definition(task)
        td.set_commands(**{key: value for (key, value) in command})
        td.set_environment(env)
        td.set_secrets(secret)

        if diff:
            print_diff(td, 'Using task definition: %s' % task)

        action.run(td, count, 'ECS Deploy')

        click.secho(
            'Successfully started %d instances of task: %s' % (
                len(action.started_tasks),
                td.family_revision
            ),
            fg='green'
        )

        for started_task in action.started_tasks:
            click.secho('- %s' % started_task['taskArn'], fg='green')
        click.secho(' ')

    except EcsError as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


def wait_for_finish(action, timeout, title, success_message, failure_message,
                    ignore_warnings):
    click.secho(title, nl=False)
    waiting = True
    waiting_timeout = datetime.now() + timedelta(seconds=timeout)
    service = action.get_service()
    inspected_until = None
    while waiting and datetime.now() < waiting_timeout:
        click.secho('.', nl=False)
        service = action.get_service()
        inspected_until = inspect_errors(
            service=service,
            failure_message=failure_message,
            ignore_warnings=ignore_warnings,
            since=inspected_until,
            timeout=False
        )
        waiting = not action.is_deployed(service)

        if waiting:
            sleep(1)

    inspect_errors(
        service=service,
        failure_message=failure_message,
        ignore_warnings=ignore_warnings,
        since=inspected_until,
        timeout=waiting
    )

    click.secho('\n%s\n' % success_message, fg='green')


def deploy_task_definition(deployment, task_definition, title, success_message,
                           failure_message, timeout, deregister,
                           previous_task_definition, ignore_warnings):
    click.secho('Updating service')
    deployment.deploy(task_definition)

    message = 'Successfully changed task definition to: %s:%s\n' % (
        task_definition.family,
        task_definition.revision
    )

    click.secho(message, fg='green')

    wait_for_finish(
        action=deployment,
        timeout=timeout,
        title=title,
        success_message=success_message,
        failure_message=failure_message,
        ignore_warnings=ignore_warnings
    )

    if deregister:
        deregister_task_definition(deployment, previous_task_definition)


def get_task_definition(action, task):
    if task:
        task_definition = action.get_task_definition(task)
    else:
        task_definition = action.get_current_task_definition(action.service)
        task = task_definition.family_revision

    click.secho('Deploying based on task definition: %s\n' % task)

    return task_definition


def create_task_definition(action, task_definition):
    click.secho('Creating new task definition revision')
    new_td = action.update_task_definition(task_definition)

    click.secho(
        'Successfully created revision: %d\n' % new_td.revision,
        fg='green'
    )

    return new_td


def deregister_task_definition(action, task_definition):
    click.secho('Deregister task definition revision')
    action.deregister_task_definition(task_definition)
    click.secho(
        'Successfully deregistered revision: %d\n' % task_definition.revision,
        fg='green'
    )


def rollback_task_definition(deployment, old, new, timeout=600):
    click.secho(
        'Rolling back to task definition: %s\n' % old.family_revision,
        fg='yellow',
    )
    deploy_task_definition(
        deployment=deployment,
        task_definition=old,
        title='Deploying previous task definition',
        success_message='Rollback successful',
        failure_message='Rollback failed. Please check ECS Console',
        timeout=timeout,
        deregister=True,
        previous_task_definition=new,
        ignore_warnings=False
    )
    click.secho(
        'Deployment failed, but service has been rolled back to previous '
        'task definition: %s\n' % old.family_revision, fg='yellow', err=True
    )


def record_deployment(revision, api_key, app_id, comment, user):
    api_key = getenv('NEW_RELIC_API_KEY', api_key)
    app_id = getenv('NEW_RELIC_APP_ID', app_id)

    if not revision or not api_key or not app_id:
        return False

    user = user or getpass.getuser()

    click.secho('Recording deployment in New Relic', nl=False)

    deployment = Deployment(api_key, app_id, user)
    deployment.deploy(revision, '', comment)

    click.secho('\nDone\n', fg='green')

    return True


def print_diff(task_definition, title='Updating task definition'):
    if task_definition.diff:
        click.secho(title)
        for diff in task_definition.diff:
            click.secho(str(diff), fg='blue')
        click.secho('')


def inspect_errors(service, failure_message, ignore_warnings, since, timeout):
    error = False
    last_error_timestamp = since

    warnings = service.get_warnings(since)
    for timestamp in warnings:
        message = warnings[timestamp]
        click.secho('')
        if ignore_warnings:
            last_error_timestamp = timestamp
            click.secho(
                text='%s\nWARNING: %s' % (timestamp, message),
                fg='yellow',
                err=False
            )
            click.secho('Continuing.', nl=False)
        else:
            click.secho(
                text='%s\nERROR: %s\n' % (timestamp, message),
                fg='red',
                err=True
            )
            error = True

    if service.older_errors:
        click.secho('')
        click.secho('Older errors', fg='yellow', err=True)
        for timestamp in service.older_errors:
            click.secho(
                text='%s\n%s\n' % (timestamp, service.older_errors[timestamp]),
                fg='yellow',
                err=True
            )

    if timeout:
        error = True
        failure_message += ' due to timeout. Please see: ' \
                           'https://github.com/fabfuel/ecs-deploy#timeout'
        click.secho('')

    if error:
        raise TaskPlacementError(failure_message)

    return last_error_timestamp


ecs.add_command(deploy)
ecs.add_command(scale)
ecs.add_command(run)

if __name__ == '__main__':  # pragma: no cover
    ecs()
