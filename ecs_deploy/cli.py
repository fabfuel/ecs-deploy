import click
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
from future.types.newstr import unicode


@click.group()
def main():
    pass


@click.command()
@click.option('-t', '--task', required=True, help='Name of the task-family to deploy')
@click.option('-c', '--cluster', required=True, help='Name of the cluster')
@click.option('-s', '--service', required=True, help='Name of the service to update')
@click.option('--image', type=(unicode, unicode), multiple=True)
@click.option('--region', required=False)
@click.option('--access-key-id', required=False)
@click.option('--secret-access-key', required=False)
def redeploy(task, cluster, service, image, access_key_id, secret_access_key, region):
    images = {key: value for (key, value) in image}
    client = boto3.client('ecs', aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key, region_name=region)

    try:
        task_definition = client.describe_task_definition(taskDefinition=task)
    except ClientError:
        exit('Unable to load task definition. Please check your credentials and/or the task family name.')
    except NoCredentialsError:
        exit('Unable to locate credentials. You can configure credentials by running "aws configure".')

    task_containers = task_definition['taskDefinition'].get('containerDefinitions')
    task_volumes = task_definition['taskDefinition'].get('volumes')

    # update image definitions
    for container in task_containers:
        if container.get('name') in images:
            container['image'] = images.get(container.get('name'))

    print('Creating new task revision...', end='')

    update_task = client.register_task_definition(
        family=task,
        containerDefinitions=task_containers,
        volumes=task_volumes)

    print('done!')
    print('  \__ New revision: %d' % update_task['taskDefinition']['revision'])

    print('Updating service with new task definition...', end='')

    client.update_service(
        cluster=cluster,
        service=service,
        desiredCount=1,
        taskDefinition='%s:%d' % (task, update_task['taskDefinition']['revision'])
    )

    print('done!')


main.add_command(redeploy)

if __name__ == '__main__':
    main()
