from __future__ import print_function, absolute_import
from time import sleep

import click
from datetime import datetime, timedelta

from ecs_deploy.ecs import DeployAction, ConnectionError, ScaleAction, EcsClient


@click.group()
def main():
    pass


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
        action = DeployAction(client, cluster, service)
        task_definition = action.get_current_task_definition()

        images = {key: value for (key, value) in image}
        task_definition.set_images(tag, **images)

        commands = {key: value for (key, value) in command}
        task_definition.set_commands(**commands)

        click.secho('Updating task definition')
        for diff in task_definition.diff:
            click.secho(str(diff), fg='blue')

        new_task_definition = action.update_task_definition(task_definition)
        click.secho('Successfully created revision: %d' % new_task_definition.revision, fg='green')
        click.secho('Successfully deregistered revision: %d' % task_definition.revision, fg='green')
        click.secho('')

        click.secho('Deploying new task definition', nl=False)
        action.deploy(new_task_definition)

        waiting = True
        old_errors = {}
        check_timeout = datetime.now() + timedelta(seconds=timeout)
        while waiting and datetime.now() < check_timeout:
            if action.is_deployed():
                click.secho('')
                click.secho('Deployment successful!', fg='green')
                click.secho('')
                waiting = False
            else:
                service = action.get_service()
                for event in service.get('events'):
                    if u'unable' in event.get(u'message') and event.get(u'createdAt') >= service.deployment_updated_at:
                        click.secho('')
                        click.secho('ERROR: %s' % event.get(u'message'), fg='red', err=True)
                        exit(1)
                    elif u'unable' in event[u'message'] and event[u'createdAt'] >= service.deployment_created_at:
                        old_errors[event[u'createdAt'].isoformat()] = 'ERROR: %s' % event[u'message']

                click.secho('.', nl=False)
                sleep(2)

        if waiting:
            click.secho('')
            click.secho('Scaling failed (timeout)!', fg='red', err=True)
            click.secho('')

            click.secho('Older errors')
            for timestamp in old_errors:
                click.secho('%s %s' % (timestamp, old_errors[timestamp]), fg='yellow')

            exit(1)

    except ConnectionError as e:
        click.secho(e.message, fg='red', err=True)


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.argument('desired_count', type=int)
@click.option('--region', help='AWS region')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access yey')
@click.option('--profile', help='AWS configuration profile')
@click.option('--timeout', default=60, type=int, help='AWS configuration profile')
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
        action = ScaleAction(client, cluster, service)

        click.secho('Updating service')
        action.scale(desired_count)
        click.secho('Successfully changed desired count to: %s' % desired_count, fg='green')
        click.secho('')

        click.secho('Scaling service', nl=False)

        waiting = True
        old_errors = {}
        check_timeout = datetime.now() + timedelta(seconds=timeout)
        while waiting and datetime.now() < check_timeout:
            if action.is_deployed():
                click.secho('')
                click.secho('Scaling successful!', fg='green')
                click.secho('')
                waiting = False
            else:
                service = action.get_service()
                for event in service.get('events'):
                    if u'unable' in event.get(u'message') and event.get(u'createdAt') >= service.deployment_updated_at:
                        click.secho('')
                        click.secho('ERROR: %s' % event.get(u'message'), fg='red', err=True)
                        exit(1)
                    elif u'unable' in event[u'message'] and event[u'createdAt'] >= service.deployment_created_at:
                        old_errors[event[u'createdAt'].isoformat()] = 'ERROR: %s' % event[u'message']

                click.secho('.', nl=False)
                sleep(2)

        if waiting:
            click.secho('')
            click.secho('Scaling failed (timeout)!', fg='red', err=True)
            click.secho('')

            click.secho('Older errors')
            for timestamp in old_errors:
                click.secho('%s %s' % (timestamp, old_errors[timestamp]), fg='yellow')

            exit(1)

    except ConnectionError as e:
        click.secho(str(e), fg='red', err=True)


main.add_command(deploy)
main.add_command(scale)

if __name__ == '__main__':
    main()
