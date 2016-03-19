from __future__ import print_function, absolute_import
from time import sleep

import click
from datetime import datetime, timedelta

from ecs_deploy.ecs import DeployAction, ConnectionError, ScaleAction, EcsClient


@click.group()
def main():
    return


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.option('-t', '--tag', help='Changes the tag for ALL container images')
@click.option('-i', '--image', type=(str, str), multiple=True, help='Overwrites the image for a container')
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container')
@click.option('--region', required=False, help='AWS region')
@click.option('--access-key-id', required=False, help='AWS access key id')
@click.option('--secret-access-key', required=False, help='AWS secret access yey')
@click.option('--profile', required=False, help='AWS configuration profile')
@click.option('--timeout', required=False, default=300, type=int, help='AWS configuration profile')
def deploy(cluster, service, tag, image, command, access_key_id, secret_access_key, region, profile, timeout):
    """
    Redeploy or modify a service.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-custer') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.

    When not giving any other options, the task definition will not be changed. It will just be duplicated, so that
    all container images will be pulled and redeployed.
    """

    try:
        client = EcsClient(access_key_id, secret_access_key, region, profile)
        deployment = DeployAction(client, cluster, service)
        task_definition = deployment.get_current_task_definition(deployment.service)

        task_definition.set_images(tag, **{key: value for (key, value) in image})
        task_definition.set_commands(**{key: value for (key, value) in command})
        print_diff(task_definition)

        click.secho('Creating new task definition revision')
        new_task_definition = deployment.update_task_definition(task_definition)
        click.secho('Successfully created revision: %d' % new_task_definition.revision, fg='green')
        click.secho('Successfully deregistered revision: %d\n' % task_definition.revision, fg='green')
        click.secho('Updating service')
        deployment.deploy(new_task_definition)
        click.secho('Successfully changed task definition to: %s:%s\n' %
                    (new_task_definition.family, new_task_definition.revision), fg='green')

        wait_for_finish(deployment, timeout, 'Deploying new task definition', 'Deployment successful!')

    except Exception as e:
        click.secho('%s\n' % str(e), fg='red', err=True)


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
        client = EcsClient(access_key_id, secret_access_key, region, profile)
        scaling = ScaleAction(client, cluster, service)
        click.secho('Updating service')
        scaling.scale(desired_count)
        click.secho('Successfully changed desired count to: %s\n' % desired_count, fg='green')
        wait_for_finish(scaling, timeout, 'Scaling service', 'Scaling successful!')

    except Exception as e:
        click.secho('%s\n' % str(e), fg='red', err=True)


def wait_for_finish(action, timeout, title, success_message):
    click.secho(title, nl=False)
    waiting = True
    check_timeout = datetime.now() + timedelta(seconds=timeout)
    service = action.get_service()
    while waiting and datetime.now() < check_timeout:
        if action.is_deployed(service):
            click.secho('\n%s\n' % success_message, fg='green')
            waiting = False
        elif print_errors(service.errors):
            exit(1)
        else:
            service = action.get_service()
            click.secho('.', nl=False)
            sleep(2)

    if waiting:
        click.secho('\nScaling failed (timeout)!', fg='red', err=True)
        print_errors(service.older_errors, 'Older errors')
        exit(1)

    exit(0)


def print_diff(task_definition):
    if task_definition.diff:
        click.secho('Updating task definition')
        for diff in task_definition.diff:
            click.secho(str(diff), fg='blue')
        click.secho('')


def print_errors(errors, title=''):
    if errors:
        click.secho('\n%s' % title)
        for timestamp in errors:
            click.secho('%s\n' % errors[timestamp], fg='red', err=True)
        return True
    return False

main.add_command(deploy)
main.add_command(scale)

if __name__ == '__main__':
    main()
