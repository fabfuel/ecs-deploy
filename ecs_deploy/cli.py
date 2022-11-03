from __future__ import print_function, absolute_import

from os import getenv
from time import sleep

import click
import json
import getpass
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
from ecs_deploy import VERSION
from ecs_deploy.ecs import DeployAction, ScaleAction, RunAction, EcsClient, DiffAction, \
    TaskPlacementError, EcsError, UpdateAction, LAUNCH_TYPE_EC2, LAUNCH_TYPE_FARGATE
from ecs_deploy.newrelic import Deployment, NewRelicException
from ecs_deploy.slack import SlackNotification


@click.group()
@click.version_option(version=VERSION, prog_name='ecs-deploy')
def ecs():  # pragma: no cover
    pass


def get_client(access_key_id, secret_access_key, region, profile, assume_account, assume_role):
    return EcsClient(access_key_id, secret_access_key, region, profile, assume_account=assume_account, assume_role=assume_role)


@click.command()
@click.argument('cluster')
@click.argument('service')
@click.option('-t', '--tag', help='Changes the tag for ALL container images')
@click.option('-i', '--image', type=(str, str), multiple=True, help='Overwrites the image for a container: <container> <image>')
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-h', '--health-check', type=(str, str, int, int, int, int), multiple=True, help='Overwrites the healthcheck in a container: <container> <command> <interval> <timeout> <retries> <start_period>')
@click.option('--cpu', type=(str, int), multiple=True, help='Overwrites the cpu value for a container: <container> <cpu>')
@click.option('--memory', type=(str, int), multiple=True, help='Overwrites the memory value for a container: <container> <memory>')
@click.option('--memoryreservation', type=(str, int), multiple=True, help='Overwrites the memory reservation value for a container: <container> <memoryreservation>')
@click.option('--task-cpu', type=int, help='Overwrites the cpu value for a task: <cpu>')
@click.option('--task-memory', type=int, help='Overwrites the memory value for a task: <memory>')
@click.option('--privileged', type=(str, bool), multiple=True, help='Overwrites the privileged value for a container: <container> <privileged>')
@click.option('--essential', type=(str, bool), multiple=True, help='Overwrites the essential value for a container: <container> <essential>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('--env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load environment variables from .env-file: <container> <env file path>')
@click.option('--s3-env-file', type=(str, str), multiple=True, required=False, help='Location of .env-file in S3 in ARN format (eg arn:aws:s3:::/bucket_name/object_name): <container> <S3 ARN>')
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('--secrets-env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load secrets from .env-file: <container> <env file path>')
@click.option('-d', '--docker-label', type=(str, str, str), multiple=True, help='Adds or changes a docker label: <container> <name> <value>')
@click.option('-u', '--ulimit', type=(str, str, int, int), multiple=True, help='Adds or changes a ulimit variable in the container description (Not available for Fargate): <container> <ulimit name> <softlimit value> <hardlimit value>')
@click.option('--system-control', type=(str, str, str), multiple=True, help='Adds or changes a system control variable in the container description (Not available for Fargate): <container> <namespace> <value>')
@click.option('-p', '--port', type=(str, int, int), multiple=True, help='Adds or changes a port mappings in the container description (Not available for Fargate): <container> <container port value> <host port value>')
@click.option('-m', '--mount', type=(str, str, str), multiple=True, help='Adds or changes a mount points in the container description (Not available for Fargate): <container> <container port value> <host port value>')
@click.option('-l', '--log', type=(str, str, str, str), multiple=True, help='Adds or changes a log configuration in the container description (Not available for Fargate): <container> <log driver> <option name> <option value>')
@click.option('-r', '--role', type=str, help='Sets the task\'s role ARN: <task role ARN>')
@click.option('-x', '--execution-role', type=str, help='Sets the execution\'s role ARN: <execution role ARN>')
@click.option('--runtime-platform', type=str, nargs=2, help='Overwrites runtimePlatform: <cpuArchitecture> <operatingSystemFamily>')
@click.option('--task', type=str, help='Task definition to be deployed. Can be a task ARN or a task family with optional revision')
@click.option('--region', required=False, help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', required=False, help='AWS access key id')
@click.option('--secret-access-key', required=False, help='AWS secret access key')
@click.option('--profile', required=False, help='AWS configuration profile name')
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
@click.option('--timeout', required=False, default=300, type=int, help='Amount of seconds to wait for deployment before command fails (default: 300). To disable timeout (fire and forget) set to -1')
@click.option('--ignore-warnings', is_flag=True, help='Do not fail deployment on warnings (port already in use or insufficient memory/CPU)')
@click.option('--newrelic-apikey', required=False, help='New Relic API Key for recording the deployment. Can also be defined via environment variable NEW_RELIC_API_KEY')
@click.option('--newrelic-appid', required=False, help='New Relic App ID for recording the deployment. Can also be defined via environment variable NEW_RELIC_APP_ID')
@click.option('--newrelic-region', required=False, help='New Relic region: US or EU (default: US). Can also be defined via environment variable NEW_RELIC_REGION')
@click.option('--newrelic-revision', required=False, help='New Relic revision for recording the deployment (default: --tag value). Can also be defined via environment variable NEW_RELIC_REVISION')
@click.option('--comment', required=False, help='Description/comment for recording the deployment')
@click.option('--user', required=False, help='User who executes the deployment (used for recording)')
@click.option('--diff/--no-diff', default=True, help='Print which values were changed in the task definition (default: --diff)')
@click.option('--deregister/--no-deregister', default=True, help='Deregister or keep the old task definition (default: --deregister)')
@click.option('--rollback/--no-rollback', default=False, help='Rollback to previous revision, if deployment failed (default: --no-rollback)')
@click.option('--exclusive-env', is_flag=True, default=False, help='Set the given environment variables exclusively and remove all other pre-existing env variables from all containers')
@click.option('--exclusive-secrets', is_flag=True, default=False, help='Set the given secrets exclusively and remove all other pre-existing secrets from all containers')
@click.option('--exclusive-docker-labels', is_flag=True, default=False, help='Set the given docker labels exclusively and remove all other pre-existing docker-labels from all containers')
@click.option('--exclusive-s3-env-file', is_flag=True, default=False, help='Set the given s3 env files exclusively and remove all other pre-existing s3 env files from all containers')
@click.option('--sleep-time', default=1, type=int, help='Amount of seconds to wait between each check of the service (default: 1)')
@click.option('--slack-url', required=False, help='Webhook URL of the Slack integration. Can also be defined via environment variable SLACK_URL')
@click.option('--slack-service-match', default=".*", required=False, help='A regular expression for defining, which services should be notified. (default: .* =all). Can also be defined via environment variable SLACK_SERVICE_MATCH')
@click.option('--exclusive-ulimits', is_flag=True, default=False, help='Set the given ulimits exclusively and remove all other pre-existing ulimits from all containers')
@click.option('--exclusive-system-controls', is_flag=True, default=False, help='Set the given system controls exclusively and remove all other pre-existing system controls from all containers')
@click.option('--exclusive-ports', is_flag=True, default=False, help='Set the given port mappings exclusively and remove all other pre-existing port mappings from all containers')
@click.option('--exclusive-mounts', is_flag=True, default=False, help='Set the given mount points exclusively and remove all other pre-existing mount points from all containers')
@click.option('--volume', type=(str, str), multiple=True, required=False, help='Set volume mapping from host to container in the task definition.')
@click.option('--add-container', type=str, multiple=True, required=False, help='Add a placeholder container in the task definition.')
@click.option('--remove-container', type=str, multiple=True, required=False, help='Remove a container from the task definition.')
def deploy(cluster, service, tag, image, command, health_check, cpu, memory, memoryreservation, task_cpu, task_memory, privileged, essential, env, env_file, s3_env_file, secret, secrets_env_file, ulimit, system_control, port, mount, log, role, execution_role, runtime_platform, task, region, access_key_id, secret_access_key, profile, account, assume_role, timeout, newrelic_apikey, newrelic_appid, newrelic_region, newrelic_revision, comment, user, ignore_warnings, diff, deregister, rollback, exclusive_env, exclusive_secrets, exclusive_s3_env_file, sleep_time, exclusive_ulimits, exclusive_system_controls, exclusive_ports, exclusive_mounts, volume, add_container, remove_container, slack_url, docker_label, exclusive_docker_labels, slack_service_match='.*'):
    """
    Redeploy or modify a service.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-cluster') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.

    When not giving any other options, the task definition will not be changed.
    It will just be duplicated, so that all container images will be pulled
    and redeployed.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
        deployment = DeployAction(client, cluster, service)

        td = get_task_definition(deployment, task)
        # If there is a new container, add it at frist.
        td.add_containers(add_container)
        td.remove_containers(remove_container)
        td.set_images(tag, **{key: value for (key, value) in image})
        td.set_commands(**{key: value for (key, value) in command})
        td.set_health_checks(health_check)
        td.set_cpu(**{key: value for (key, value) in cpu})
        td.set_memory(**{key: value for (key, value) in memory})
        td.set_memoryreservation(**{key: value for (key, value) in memoryreservation})
        td.set_task_cpu(task_cpu)
        td.set_task_memory(task_memory)
        td.set_privileged(**{key: value for (key, value) in privileged})
        td.set_essential(**{key: value for (key, value) in essential})
        td.set_environment(env, exclusive_env, env_file)
        td.set_docker_labels(docker_label, exclusive_docker_labels)
        td.set_s3_env_file(s3_env_file, exclusive_s3_env_file)
        td.set_secrets(secret, exclusive_secrets, secrets_env_file)
        td.set_ulimits(ulimit, exclusive_ulimits)
        td.set_system_controls(system_control, exclusive_system_controls)
        td.set_port_mappings(port, exclusive_ports)
        td.set_mount_points(mount, exclusive_mounts)
        td.set_log_configurations(log)
        td.set_role_arn(role)
        td.set_execution_role_arn(execution_role)
        td.set_runtime_platform(runtime_platform)
        td.set_volumes(volume)

        slack = SlackNotification(
            getenv('SLACK_URL', slack_url),
            getenv('SLACK_SERVICE_MATCH', slack_service_match)
        )
        slack.notify_start(cluster, tag, td, comment, user, service=service)

        click.secho('Deploying based on task definition: %s\n' % td.family_revision)

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
                sleep_time=sleep_time
            )

        except TaskPlacementError as e:
            slack.notify_failure(cluster, str(e), service=service)
            if rollback:
                click.secho('%s\n' % str(e), fg='red', err=True)
                rollback_task_definition(deployment, td, new_td, sleep_time=sleep_time)
                exit(1)
            else:
                raise

        record_deployment(tag, newrelic_apikey, newrelic_appid, newrelic_region, newrelic_revision, comment, user)

        slack.notify_success(cluster, td.revision, service=service)

    except (EcsError, NewRelicException, ClientError) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('task')
@click.argument('rule')
@click.option('-i', '--image', type=(str, str), multiple=True, help='Overwrites the image for a container: <container> <image>')
@click.option('-t', '--tag', help='Changes the tag for ALL container images')
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('--cpu', type=(str, int), multiple=True, help='Overwrites the cpu value for a container: <container> <cpu>')
@click.option('--memory', type=(str, int), multiple=True, help='Overwrites the memory value for a container: <container> <memory>')
@click.option('--memoryreservation', type=(str, int), multiple=True, help='Overwrites the memory reservation value for a container: <container> <memoryreservation>')
@click.option('--task-cpu', type=int, help='Overwrites the cpu value for a task: <cpu>')
@click.option('--task-memory', type=int, help='Overwrites the memory value for a task: <memory>')
@click.option('--privileged', type=(str, bool), multiple=True, help='Overwrites the memory reservation value for a container: <container> <memoryreservation>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('--secrets-env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load secrets from .env-file: <container> <env file path>')
@click.option('-d', '--docker-label', type=(str, str, str), multiple=True, help='Adds or changes a docker label: <container> <name> <value>')
@click.option('-u', '--ulimit', type=(str, str, int, int), multiple=True, help='Adds or changes a ulimit variable in the container description (Not available for Fargate): <container> <ulimit name> <softlimit value> <hardlimit value>')
@click.option('--system-control', type=(str, str, str), multiple=True, help='Adds or changes a system control variable in the container description (Not available for Fargate): <container> <namespace> <value>')
@click.option('-p', '--port', type=(str, int, int), multiple=True, help='Adds or changes a port mappings in the container description (Not available for Fargate): <container> <container port value> <host port value>')
@click.option('-m', '--mount', type=(str, str, str), multiple=True, help='Adds or changes a mount points in the container description (Not available for Fargate): <container> <container port value> <host port value>')
@click.option('-l', '--log', type=(str, str, str, str), multiple=True, help='Adds or changes a log configuration in the container description (Not available for Fargate): <container> <log driver> <option name> <option value>')
@click.option('--env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load environment variables from .env-file')
@click.option('--s3-env-file', type=(str, str), multiple=True, required=False, help='Location of .env-file in S3 in ARN format (eg arn:aws:s3:::/bucket_name/object_name')
@click.option('-r', '--role', type=str, help='Sets the task\'s role ARN: <task role ARN>')
@click.option('-x', '--execution-role', type=str, help='Sets the execution\'s role ARN: <execution role ARN>')
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--newrelic-apikey', required=False, help='New Relic API Key for recording the deployment. Can also be defined via environment variable NEW_RELIC_API_KEY')
@click.option('--newrelic-appid', required=False, help='New Relic App ID for recording the deployment. Can also be defined via environment variable NEW_RELIC_APP_ID')
@click.option('--newrelic-region', required=False, help='New Relic region: US or EU (default: US). Can also be defined via environment variable NEW_RELIC_REGION')
@click.option('--newrelic-revision', required=False, help='New Relic revision for recording the deployment (default: --tag value). Can also be defined via environment variable NEW_RELIC_REVISION')
@click.option('--comment', required=False, help='Description/comment for recording the deployment')
@click.option('--user', required=False, help='User who executes the deployment (used for recording)')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
@click.option('--diff/--no-diff', default=True, help='Print what values were changed in the task definition')
@click.option('--deregister/--no-deregister', default=True, help='Deregister or keep the old task definition (default: --deregister)')
@click.option('--rollback/--no-rollback', default=False, help='Rollback to previous revision, if deployment failed (default: --no-rollback)')
@click.option('--exclusive-env', is_flag=True, default=False, help='Set the given environment variables exclusively and remove all other pre-existing env variables from all containers')
@click.option('--exclusive-secrets', is_flag=True, default=False, help='Set the given secrets exclusively and remove all other pre-existing secrets from all containers')
@click.option('--exclusive-docker-labels', is_flag=True, default=False, help='Set the given docker labels exclusively and remove all other pre-existing docker-labels from all containers')
@click.option('--exclusive-s3-env-file', is_flag=True, default=False, help='Set the given s3 env files exclusively and remove all other pre-existing s3 env files from all containers')
@click.option('--slack-url', required=False, help='Webhook URL of the Slack integration. Can also be defined via environment variable SLACK_URL')
@click.option('--slack-service-match', default=".*", required=False, help='A regular expression for defining, deployments of which crons should be notified. (default: .* =all). Can also be defined via environment variable SLACK_SERVICE_MATCH')
@click.option('--exclusive-ulimits', is_flag=True, default=False, help='Set the given ulimits exclusively and remove all other pre-existing ulimits from all containers')
@click.option('--exclusive-system-controls', is_flag=True, default=False, help='Set the given system controls exclusively and remove all other pre-existing system controls from all containers')
@click.option('--exclusive-ports', is_flag=True, default=False, help='Set the given port mappings exclusively and remove all other pre-existing port mappings from all containers')
@click.option('--exclusive-mounts', is_flag=True, default=False, help='Set the given mount points exclusively and remove all other pre-existing mount points from all containers')
@click.option('--volume', type=(str, str), multiple=True, required=False, help='Set volume mapping from host to container in the task definition.')
def cron(cluster, task, rule, image, tag, command, cpu, memory, memoryreservation, task_cpu, task_memory, privileged, env, env_file, s3_env_file, secret, secrets_env_file, ulimit, system_control, port, mount, log, role, execution_role, region, access_key_id, secret_access_key, newrelic_apikey, newrelic_appid, newrelic_region, newrelic_revision, comment, user, profile, account, assume_role, diff, deregister, rollback, exclusive_env, exclusive_secrets, exclusive_s3_env_file, slack_url, slack_service_match, exclusive_ulimits, exclusive_system_controls, exclusive_ports, exclusive_mounts, volume, docker_label, exclusive_docker_labels):
    """
    Update a scheduled task.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-cluster') within ECS.
    TASK is the name of your task definition (e.g. 'my-task') within ECS.
    RULE is the name of the rule to use the new task definition.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
        action = RunAction(client, cluster)

        td = action.get_task_definition(task)
        click.secho('Update task definition based on: %s\n' % td.family_revision)

        td.set_images(tag, **{key: value for (key, value) in image})
        td.set_commands(**{key: value for (key, value) in command})
        td.set_cpu(**{key: value for (key, value) in cpu})
        td.set_memory(**{key: value for (key, value) in memory})
        td.set_memoryreservation(**{key: value for (key, value) in memoryreservation})
        td.set_task_cpu(task_cpu)
        td.set_task_memory(task_memory)
        td.set_privileged(**{key: value for (key, value) in privileged})
        td.set_environment(env, exclusive_env, env_file)
        td.set_docker_labels(docker_label, exclusive_docker_labels)
        td.set_s3_env_file(s3_env_file, exclusive_s3_env_file)
        td.set_secrets(secret, exclusive_secrets, secrets_env_file)
        td.set_ulimits(ulimit, exclusive_ulimits)
        td.set_system_controls(system_control, exclusive_system_controls)
        td.set_port_mappings(port, exclusive_ports)
        td.set_mount_points(mount, exclusive_mounts)
        td.set_log_configurations(log)
        td.set_role_arn(role)
        td.set_execution_role_arn(execution_role)
        td.set_volumes(volume)

        slack = SlackNotification(
            getenv('SLACK_URL', slack_url),
            getenv('SLACK_SERVICE_MATCH', slack_service_match)
        )
        slack.notify_start(cluster, tag, td, comment, user, rule=rule)

        if diff:
            print_diff(td)

        new_td = create_task_definition(action, td)

        client.update_rule(
            cluster=cluster,
            rule=rule,
            task_definition=new_td
        )
        click.secho('Updating scheduled task')
        click.secho('Successfully updated scheduled task %s\n' % rule, fg='green')

        slack.notify_success(cluster, td.revision, rule=rule)

        record_deployment(tag, newrelic_apikey, newrelic_appid, newrelic_region, newrelic_revision, comment, user)

        if deregister:
            deregister_task_definition(action, td)

    except (EcsError, ClientError) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('task')
@click.option('-i', '--image', type=(str, str), multiple=True, help='Overwrites the image for a container: <container> <image>')
@click.option('-t', '--tag', help='Changes the tag for ALL container images')
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('--env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load environment variables from .env-file')
@click.option('--s3-env-file', type=(str, str), multiple=True, required=False, help='Location of .env-file in S3 in ARN format (eg arn:aws:s3:::/bucket_name/object_name')
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('--secrets-env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load secrets from .env-file: <container> <env file path>')
@click.option('-d', '--docker-label', type=(str, str, str), multiple=True, help='Adds or changes a docker label: <container> <name> <value>')
@click.option('-r', '--role', type=str, help='Sets the task\'s role ARN: <task role ARN>')
@click.option('--runtime-platform', type=str, nargs=2, help='Overwrites runtimePlatform: <cpuArchitecture> <operatingSystemFamily>')
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
@click.option('--diff/--no-diff', default=True, help='Print what values were changed in the task definition')
@click.option('--exclusive-env', is_flag=True, default=False, help='Set the given environment variables exclusively and remove all other pre-existing env variables from all containers')
@click.option('--exclusive-secrets', is_flag=True, default=False, help='Set the given secrets exclusively and remove all other pre-existing secrets from all containers')
@click.option('--exclusive-docker-labels', is_flag=True, default=False, help='Set the given docker labels exclusively and remove all other pre-existing docker-labels from all containers')
@click.option('--exclusive-s3-env-file', is_flag=True, default=False, help='Set the given s3 env files exclusively and remove all other pre-existing s3 env files from all containers')
@click.option('--deregister/--no-deregister', default=True, help='Deregister or keep the old task definition (default: --deregister)')
def update(task, image, tag, command, env, env_file, s3_env_file, secret, secrets_env_file, role, region, access_key_id, secret_access_key, profile, account, assume_role, diff, exclusive_env, exclusive_s3_env_file, exclusive_secrets, runtime_platform, deregister, docker_label, exclusive_docker_labels):
    """
    Update a task definition.

    \b
    TASK is the name of your task definition family (e.g. 'my-task') within ECS.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
        action = UpdateAction(client)

        td = action.get_task_definition(task)
        click.secho('Update task definition based on: %s\n' % td.family_revision)

        td.set_images(tag, **{key: value for (key, value) in image})
        td.set_commands(**{key: value for (key, value) in command})
        td.set_environment(env, exclusive_env, env_file)
        td.set_docker_labels(docker_label, exclusive_docker_labels)
        td.set_secrets(secret, exclusive_secrets, secrets_env_file)
        td.set_s3_env_file(s3_env_file, exclusive_s3_env_file)
        td.set_role_arn(role)
        td.set_runtime_platform(runtime_platform)

        if diff:
            print_diff(td)

        create_task_definition(action, td)

        if deregister:
            deregister_task_definition(action, td)

    except (EcsError, ClientError) as e:
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
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
@click.option('--timeout', default=300, type=int, help='Amount of seconds to wait for deployment before command fails (default: 300). To disable timeout (fire and forget) set to -1')
@click.option('--ignore-warnings', is_flag=True, help='Do not fail deployment on warnings (port already in use or insufficient memory/CPU)')
@click.option('--sleep-time', default=1, type=int, help='Amount of seconds to wait between each check of the service (default: 1)')
def scale(cluster, service, desired_count, access_key_id, secret_access_key, region, profile, account, assume_role, timeout, ignore_warnings, sleep_time):
    """
    Scale a service up or down.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-cluster') within ECS.
    SERVICE is the name of your service (e.g. 'my-app') within ECS.
    DESIRED_COUNT is the number of tasks your service should run.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
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
            ignore_warnings=ignore_warnings,
            sleep_time=sleep_time
        )

    except (EcsError, ClientError) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('cluster')
@click.argument('task')
@click.argument('count', required=False, default=1)
@click.option('-c', '--command', type=(str, str), multiple=True, help='Overwrites the command in a container: <container> <command>')
@click.option('-e', '--env', type=(str, str, str), multiple=True, help='Adds or changes an environment variable: <container> <name> <value>')
@click.option('--env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load environment variables from .env-file')
@click.option('--s3-env-file', type=(str, str), multiple=True, required=False, help='Location of .env-file in S3 in ARN format (eg arn:aws:s3:::/bucket_name/object_name')
@click.option('-s', '--secret', type=(str, str, str), multiple=True, help='Adds or changes a secret environment variable from the AWS Parameter Store (Not available for Fargate): <container> <name> <parameter name>')
@click.option('--secrets-env-file', type=(str, str), default=((None, None),), multiple=True, required=False, help='Load secrets from .env-file: <container> <env file path>')
@click.option('-d', '--docker-label', type=(str, str, str), multiple=True, help='Adds or changes a docker label: <container> <name> <value>')
@click.option('--launchtype', type=click.Choice([LAUNCH_TYPE_EC2, LAUNCH_TYPE_FARGATE]), default=LAUNCH_TYPE_EC2, help='ECS Launch type (default: EC2)')
@click.option('--subnet', type=str, multiple=True, help='A subnet ID to launch the task within. Required for launch type FARGATE (multiple values possible)')
@click.option('--securitygroup', type=str, multiple=True, help='A security group ID to launch the task within. Required for launch type FARGATE (multiple values possible)')
@click.option('--public-ip', is_flag=True, default=False, help='Should a public IP address be assigned to the task (default: False)')
@click.option('--platform-version', help='The version of the Fargate platform on which to run the task. Optional, FARGATE launch type only.', required=False)
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
@click.option('--exclusive-env', is_flag=True, default=False, help='Set the given environment variables exclusively and remove all other pre-existing env variables from all containers')
@click.option('--exclusive-secrets', is_flag=True, default=False, help='Set the given secrets exclusively and remove all other pre-existing secrets from all containers')
@click.option('--exclusive-docker-labels', is_flag=True, default=False, help='Set the given docker labels exclusively and remove all other pre-existing docker-labels from all containers')
@click.option('--exclusive-s3-env-file', is_flag=True, default=False, help='Set the given s3 env files exclusively and remove all other pre-existing s3 env files from all containers')
@click.option('--diff/--no-diff', default=True, help='Print what values were changed in the task definition')
def run(cluster, task, count, command, env, env_file, s3_env_file, secret, secrets_env_file, launchtype, subnet, securitygroup, public_ip, platform_version, region, access_key_id, secret_access_key, profile, account, assume_role, exclusive_env, exclusive_secrets, exclusive_s3_env_file, diff, docker_label, exclusive_docker_labels):
    """
    Run a one-off task.

    \b
    CLUSTER is the name of your cluster (e.g. 'my-cluster') within ECS.
    TASK is the name of your task definition (e.g. 'my-task') within ECS.
    COUNT is the number of tasks your service should run.
    """
    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
        action = RunAction(client, cluster)

        td = action.get_task_definition(task)
        td.set_commands(**{key: value for (key, value) in command})
        td.set_environment(env, exclusive_env, env_file)
        td.set_docker_labels(docker_label, exclusive_docker_labels)
        td.set_s3_env_file(s3_env_file, exclusive_s3_env_file)
        td.set_secrets(secret, exclusive_secrets, secrets_env_file)

        if diff:
            print_diff(td, 'Using task definition: %s' % task)

        action.run(td, count, 'ECS Deploy', launchtype, subnet, securitygroup, public_ip, platform_version)

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

    except (EcsError, ClientError) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


@click.command()
@click.argument('task')
@click.argument('revision_a')
@click.argument('revision_b')
@click.option('--region', help='AWS region (e.g. eu-central-1)')
@click.option('--access-key-id', help='AWS access key id')
@click.option('--secret-access-key', help='AWS secret access key')
@click.option('--profile', help='AWS configuration profile name')
@click.option('--account', help='Target AWS account id to deploy in')
@click.option('--assume-role', help='AWS Role to assume in target account')
def diff(task, revision_a, revision_b, region, access_key_id, secret_access_key, profile, account, assume_role):
    """
    Compare two task definition revisions.

    \b
    TASK is the name of your task definition (e.g. 'my-task') within ECS.
    COUNT is the number of tasks your service should run.
    """

    try:
        client = get_client(access_key_id, secret_access_key, region, profile, account, assume_role)
        action = DiffAction(client)

        td_a = action.get_task_definition('%s:%s' % (task, revision_a))
        td_b = action.get_task_definition('%s:%s' % (task, revision_b))

        result = td_a.diff_raw(td_b)
        for difference in result:
            if difference[0] == 'add':
                click.secho('%s: %s' % (difference[0], difference[1]), fg='green')
                for added in difference[2]:
                    click.secho('    + %s: %s' % (added[0], json.dumps(added[1])), fg='green')

            if difference[0] == 'change':
                click.secho('%s: %s' % (difference[0], difference[1]), fg='yellow')
                click.secho('    - %s' % json.dumps(difference[2][0]), fg='red')
                click.secho('    + %s' % json.dumps(difference[2][1]), fg='green')

            if difference[0] == 'remove':
                click.secho('%s: %s' % (difference[0], difference[1]), fg='red')
                for removed in difference[2]:
                    click.secho('    - %s: %s' % removed, fg='red')

    except (EcsError, ClientError) as e:
        click.secho('%s\n' % str(e), fg='red', err=True)
        exit(1)


def wait_for_finish(action, timeout, title, success_message, failure_message,
                    ignore_warnings, sleep_time=1):
    click.secho(title)
    start_timestamp = datetime.now()
    waiting_timeout = datetime.now() + timedelta(seconds=timeout)
    service = action.get_service()
    inspected_until = None

    if timeout == -1:
        waiting = False
    else:
        waiting = True

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
            sleep(sleep_time)

    inspect_errors(
        service=service,
        failure_message=failure_message,
        ignore_warnings=ignore_warnings,
        since=inspected_until,
        timeout=waiting
    )

    click.secho('\n%s' % success_message, fg='green')
    click.secho('Duration: %s sec\n' % (datetime.now() - start_timestamp).seconds)


def deploy_task_definition(deployment, task_definition, title, success_message,
                           failure_message, timeout, deregister,
                           previous_task_definition, ignore_warnings, sleep_time):
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
        ignore_warnings=ignore_warnings,
        sleep_time=sleep_time
    )

    if deregister:
        deregister_task_definition(deployment, previous_task_definition)


def get_task_definition(action, task):
    if task:
        task_definition = action.get_task_definition(task)
    else:
        task_definition = action.get_current_task_definition(action.service)
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


def rollback_task_definition(deployment, old, new, timeout=600, sleep_time=1):
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
        ignore_warnings=False,
        sleep_time=sleep_time
    )
    click.secho(
        'Deployment failed, but service has been rolled back to previous '
        'task definition: %s\n' % old.family_revision, fg='yellow', err=True
    )


def record_deployment(tag, api_key, app_id, region, revision, comment, user):
    api_key = getenv('NEW_RELIC_API_KEY', api_key)
    app_id = getenv('NEW_RELIC_APP_ID', app_id)
    region = getenv('NEW_RELIC_REGION', region)
    revision = getenv('NEW_RELIC_REVISION', revision) or tag

    if not revision or not api_key or not app_id:
        if api_key:
            click.secho('Missing required parameters for recording New Relic deployment.' \
                        'Please see https://github.com/fabfuel/ecs-deploy#new-relic')
        return False

    user = user or getpass.getuser()

    click.secho('Recording deployment in New Relic', nl=False)

    deployment = Deployment(api_key, app_id, user, region)
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
                '%s\nWARNING: %s' % (timestamp, message),
                fg='yellow',
                err=False
            )
            click.secho('Continuing.', nl=False)
        else:
            click.secho(
                '%s\nERROR: %s\n' % (timestamp, message),
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
ecs.add_command(cron)
ecs.add_command(update)
ecs.add_command(diff)

if __name__ == '__main__':  # pragma: no cover
    ecs()
