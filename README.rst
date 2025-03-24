ECS Deploy
----------

.. image:: https://badge.fury.io/py/ecs-deploy.svg
    :target: https://badge.fury.io/py/ecs-deploy

.. image:: https://github.com/fabfuel/ecs-deploy/actions/workflows/build.yml/badge.svg
    :target: https://github.com/fabfuel/ecs-deploy/actions/workflows/build.yml

`ecs-deploy` simplifies deployments on Amazon ECS by providing a convenience CLI tool for complex actions, which are executed pretty often.

Key Features
------------
- support for complex task definitions (e.g. multiple containers & task role)
- easily redeploy the current task definition (including `docker pull` of eventually updated images)
- deploy new versions/tags or all containers or just a single container in your task definition
- scale up or down by adjusting the desired count of running tasks
- add or adjust containers environment variables
- run one-off tasks from the CLI
- automatically monitor deployments in New Relic

TL;DR
-----
Deploy a new version of your service::

    $ ecs deploy my-cluster my-service --tag 1.2.3

Redeploy the current version of a service::

    $ ecs deploy my-cluster my-service

Scale up or down a service::

    $ ecs scale my-cluster my-service 4

Updating a cron job::

    $ ecs cron my-cluster my-task my-rule

Update a task definition (without running or deploying)::

    $ ecs update my-task


Installation
------------

The project is available on PyPI. Simply run::

    $ pip install ecs-deploy

For [Homebrew](https://brew.sh/) users, you can also install [it](https://formulae.brew.sh/formula/ecs-deploy) via brew::

    $ brew install ecs-deploy

Run via Docker
--------------
Instead of installing **ecs-deploy** locally, which requires a Python environment, you can run **ecs-deploy** via Docker. All versions starting from 1.7.1 are available on Docker Hub: https://cloud.docker.com/repository/docker/fabfuel/ecs-deploy

Running **ecs-deploy** via Docker is easy as::

    docker run fabfuel/ecs-deploy:1.10.2

In this example, the stable version 1.10.2 is executed. Alternatively you can use Docker tags ``master`` or ``latest`` for the latest stable version or Docker tag ``develop`` for the newest development version of **ecs-deploy**.

Please be aware, that when running **ecs-deploy** via Docker, the configuration - as described below - does not apply. You have to provide credentials and the AWS region via the command as attributes or environment variables::

    docker run fabfuel/ecs-deploy:1.10.2 ecs deploy my-cluster my-service --region eu-central-1 --access-key-id ABC --secret-access-key ABC


Configuration
-------------
As **ecs-deploy** is based on boto3 (the official AWS Python library), there are several ways to configure and store the
authentication credentials. Please read the boto3 documentation for more details
(http://boto3.readthedocs.org/en/latest/guide/configuration.html#configuration). The simplest way is by running::

    $ aws configure

Alternatively you can pass the AWS credentials (via `--access-key-id` and `--secret-access-key`) or the AWS
configuration profile (via `--profile`) as options when you run `ecs`.

AWS IAM
-------

If you are using **ecs-deploy** with a role or user account that does not have full AWS access, such as in a deploy script, you will
need to use or create an IAM policy with the correct set of permissions in order for your deploys to succeed. One option is to use the
pre-specified ``AmazonECS_FullAccess`` (https://docs.aws.amazon.com/AmazonECS/latest/userguide/security-iam-awsmanpol.html#security-iam-awsmanpol-AmazonECS_FullAccess) policy. If you would prefer to create a role with a more minimal set of permissions,
the following are required:

* ``ecs:ListServices``
* ``ecs:UpdateService``
* ``ecs:ListTasks``
* ``ecs:RegisterTaskDefinition``
* ``ecs:DescribeServices``
* ``ecs:DescribeTasks``
* ``ecs:ListTaskDefinitions``
* ``ecs:DescribeTaskDefinition``
* ``ecs:DeregisterTaskDefinition``

If using custom IAM permissions, you will also need to set the ``iam:PassRole`` policy for each IAM role. See here https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_passrole.html for more information.

Note that not every permission is required for every action you can take in **ecs-deploy**. You may be able to adjust permissions based on your specific needs.

Actions
-------
Currently the following actions are supported:

deploy
======
Redeploy a service either without any modifications or with a new image, environment variable, docker label, and/or command definition.

scale
=====
Scale a service up or down and change the number of running tasks.

run
===
Run a one-off task based on an existing task-definition and optionally override command, environment variables and/or docker labels.

update
======
Update a task definition by creating a new revision to set a new image,
environment variable, docker label, and/or command definition, etc.

cron (scheduled task)
=====================
Update a task definition and update a events rule (scheduled task) to use the
new task definition.


Usage
-----

For detailed information about the available actions, arguments and options, run::

    $ ecs deploy --help
    $ ecs scale --help
    $ ecs run --help

Examples
--------
All examples assume, that authentication has already been configured.

Deployment
----------

Simple Redeploy
===============
To redeploy a service without any modifications, but pulling the most recent image versions, run the following command.
This will duplicate the current task definition and cause the service to redeploy all running tasks.::

    $ ecs deploy my-cluster my-service


Deploy a new tag
================
To change the tag for **all** images in **all** containers in the task definition, run the following command::

    $ ecs deploy my-cluster my-service -t 1.2.3


Deploy a new image
==================
To change the image of a specific container, run the following command::

    $ ecs deploy my-cluster my-service --image webserver nginx:1.11.8

This will modify the **webserver** container only and change its image to "nginx:1.11.8".


Deploy several new images
=========================
The `-i` or `--image` option can also be passed several times::

    $ ecs deploy my-cluster my-service -i webserver nginx:1.9 -i application my-app:1.2.3

This will change the **webserver**'s container image to "nginx:1.9" and the **application**'s image to "my-app:1.2.3".

Deploy a custom task definition
===============================
To deploy any task definition (independent of which is currently used in the service), you can use the ``--task`` parameter. The value can be:

A fully qualified task ARN::

    $ ecs deploy my-cluster my-service --task arn:aws:ecs:eu-central-1:123456789012:task-definition/my-task:20

A task family name with revision::

    $ ecs deploy my-cluster my-service --task my-task:20

Or just a task family name. It this case, the most recent revision is used::

    $ ecs deploy my-cluster my-service --task my-task

.. important::
   ``ecs`` will still create a new task definition, which then is used in the service.
   This is done, to retain consistent behaviour and to ensure the ECS agent e.g. pulls all images.
   But the newly created task definition will be based on the given task, not the currently used task.


Set an environment variable
===========================
To add a new or adjust an existing environment variable of a specific container, run the following command::

    $ ecs deploy my-cluster my-service -e webserver SOME_VARIABLE SOME_VALUE

This will modify the **webserver** container definition and add or overwrite the environment variable `SOME_VARIABLE` with the value "SOME_VALUE". This way you can add new or adjust already existing environment variables.


Adjust multiple environment variables
=====================================
You can add or change multiple environment variables at once, by adding the `-e` (or `--env`) options several times::

    $ ecs deploy my-cluster my-service -e webserver SOME_VARIABLE SOME_VALUE -e webserver OTHER_VARIABLE OTHER_VALUE -e app APP_VARIABLE APP_VALUE

This will modify the definition **of two containers**.
The **webserver**'s environment variable `SOME_VARIABLE` will be set to "SOME_VALUE" and the variable `OTHER_VARIABLE` to "OTHER_VALUE".
The **app**'s environment variable `APP_VARIABLE` will be set to "APP_VALUE".


Set environment variables exclusively, remove all other pre-existing environment variables
==========================================================================================
To reset all existing environment variables of a task definition, use the flag ``--exclusive-env`` ::

    $ ecs deploy my-cluster my-service -e webserver SOME_VARIABLE SOME_VALUE --exclusive-env

This will remove **all other** existing environment variables of **all containers** of the task definition, except for the variable `SOME_VARIABLE` with the value "SOME_VALUE" in the webserver container.


Set a secret environment variable from the AWS Parameter Store
==============================================================

.. important::
    This option was introduced by AWS in ECS Agent v1.22.0. Make sure your ECS agent version is >= 1.22.0 or else your task will not deploy.

To add a new or adjust an existing secret of a specific container, run the following command::

    $ ecs deploy my-cluster my-service -s webserver SOME_SECRET KEY_OF_SECRET_IN_PARAMETER_STORE

You can also specify the full arn of the parameter::

    $ ecs deploy my-cluster my-service -s webserver SOME_SECRET arn:aws:ssm:<aws region>:<aws account id>:parameter/KEY_OF_SECRET_IN_PARAMETER_STORE

This will modify the **webserver** container definition and add or overwrite the environment variable `SOME_SECRET` with the value of the `KEY_OF_SECRET_IN_PARAMETER_STORE` in the AWS Parameter Store of the AWS Systems Manager.


Set secrets exclusively, remove all other pre-existing secret environment variables
===================================================================================
To reset all existing secrets (secret environment variables) of a task definition, use the flag ``--exclusive-secrets`` ::

    $ ecs deploy my-cluster my-service -s webserver NEW_SECRET KEY_OF_SECRET_IN_PARAMETER_STORE --exclusive-secret

This will remove **all other** existing secret environment variables of **all containers** of the task definition, except for the new secret variable `NEW_SECRET` with the value coming from the AWS Parameter Store with the name "KEY_OF_SECRET_IN_PARAMETER_STORE" in the webserver container.


Set environment via .env files
==============================
Instead of setting environment variables separately, you can pass a .env file per container to set the whole environment at once. You can either point to a local file or a file stored on S3, via::

    $ ecs deploy my-cluster my-service --env-file my-app env/my-app.env

    $ ecs deploy my-cluster my-service --s3-env-file my-app arn:aws:s3:::my-ecs-environment/my-app.env

Set secrets via .env files
==============================
Instead of setting secrets separately, you can pass a .env file per container to set all secrets at once.

This will expect an env file format, but any values will be set as the `valueFrom` parameter in the secrets config.
This value can be either the path or the full ARN of a secret in the AWS Parameter Store. For example, with a secrets.env
file like the following:

```
SOME_SECRET=arn:aws:ssm:<aws region>:<aws account id>:parameter/KEY_OF_SECRET_IN_PARAMETER_STORE
```

$ ecs deploy my-cluster my-service --secret-env-file webserver env/secrets.env

This will modify the **webserver** container definition and add or overwrite the environment variable `SOME_SECRET` with the value of the `KEY_OF_SECRET_IN_PARAMETER_STORE` in the AWS Parameter Store of the AWS Systems Manager.


Set a docker label
===================
To add a new or adjust an existing docker labels of a specific container, run the following command::

    $ ecs deploy my-cluster my-service -d webserver somelabel somevalue

This will modify the **webserver** container definition and add or overwrite the docker label "somelabel" with the value "somevalue". This way you can add new or adjust already existing docker labels.


Adjust multiple docker labels
=============================
You can add or change multiple docker labels at once, by adding the `-d` (or `--docker-label`) options several times::

    $ ecs deploy my-cluster my-service -d webserver somelabel somevalue -d webserver otherlabel othervalue -d app applabel appvalue

This will modify the definition **of two containers**.
The **webserver**'s docker label "somelabel" will be set to "somevalue" and the label "otherlabel" to "othervalue".
The **app**'s docker label "applabel" will be set to "appvalue".


Set docker labels exclusively, remove all other pre-existing docker labels
==========================================================================
To reset all existing docker labels of a task definition, use the flag ``--exclusive-docker-labels`` ::

    $ ecs deploy my-cluster my-service -d webserver somelabel somevalue --exclusive-docker-labels

This will remove **all other** existing docker labels of **all containers** of the task definition, except for the label "somelabel" with the value "somevalue" in the webserver container.


Modify a command
================
To change the command of a specific container, run the following command::

    $ ecs deploy my-cluster my-service --command webserver "nginx"

This will modify the **webserver** container and change its command to "nginx". If you have
a command that requires arguments as well, then you can simply specify it like this as you would normally do:

    $ ecs deploy my-cluster my-service --command webserver "ngnix -c /etc/ngnix/ngnix.conf"

This works fine as long as any of the arguments do not contain any spaces. In case arguments to the
command itself contain spaces, then you can use the JSON format:

$ ecs deploy my-cluster my-service --command webserver '["sh", "-c", "while true; do echo Time files like an arrow $(date); sleep 1; done;"]'

More about this can be looked up in documentation.
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html#container_definitions




Set a task role
===============
To change or set the role, the service's task should run as, use the following command::

    $ ecs deploy my-cluster my-service -r arn:aws:iam::123456789012:role/MySpecialEcsTaskRole

This will set the task role to "MySpecialEcsTaskRole".


Set CPU and memory reservation
==============================
- Set the `cpu` value for a task: :code:`--task-cpu 0`.
- Set the `cpu` value for a task container: :code:`--cpu <container_name> 0`.
- Set the `memory` value (`hard limit`) for a task: :code:`--task-memory 256`.
- Set the `memory` value (`hard limit`) for a task container: :code:`--memory <container_name> 256`.
- Set the `memoryreservation` value (`soft limit`) for a task definition: :code:`--memoryreservation <container_name> 256`.

Set privileged or essential flags
=================================
- Set the `privileged` value for a task definition: :code:`--privileged <container_name> True|False`.
- Set the `essential` value for a task definition: :code:`--essential <container_name> True|False`.

Set logging configuration
=========================
Set the `logConfiguration` values for a task definition::

    --log <container_name> awslogs awslogs-group <log_group_name>
    --log <container_name> awslogs awslogs-region <region>
    --log <container_name> awslogs awslogs-stream-prefix <stream_prefix>


Set port mapping
================
- Set the `port mappings` values for a task definition: :code:`--port <container_name> <container_port> <host_port>`.

  - Supports :code:`--exclusive-ports`.
  - The `protocol` is fixed to `tcp`.

Set volumes & mount points
==========================
- Set the `volumes` values for a task definition :code:`--volume <volume_name> /host/path`.

  - :code:`<volume_name>` can then be used with  :code:`--mount`.
- Set the `mount points` values for a task definition: :code:`--mount <container_name> <volume_name> /container/path`.

  - Supports :code:`--exclusive-mounts`.

  - :code:`<volume_name>` is the one set by :code:`--volume`.
- Set the `ulimits` values for a task definition: :code:`--ulimit <container_name> memlock 67108864 67108864`.

  - Supports :code:`--exclusive-ulimits`.
- Set the `systemControls` values for a task definition: :code:`--system-control <container_name> net.core.somaxconn 511`.

  - Supports :code:`--exclusive-system-controls`.
- Set the `healthCheck` values for a task definition: :code:`--health-check <container_name> <command> <interval> <timeout> <retries> <start_period>`.


Set Health Checks
=================
  - Example :code:`--health-check webserver "curl -f http://localhost/alive/" 30 5 3 0`


Placeholder Container
=====================
- Add placeholder containers: :code:`--add-container <container_name>`.
- To comply with the minimum requirements for a task definition, a placeholder container is set like this:
    + The container name is :code:`<container_name>`.
    + The container image is :code:`PLACEHOLDER`.
    + The container soft limit is :code:`128`.
- The idea is to set sensible values with the deployment.

It is possible to add and define a new container with the same deployment::

      --add-container redis --image redis redis:6 --port redis 6379 6379

Remove containers
=================
- Containers can be removed: :code:`--remove-container <container_name>`.

  - Leaves the original containers, if all containers would be removed.


All but the container flags can be used with `ecs deploy` and `ecs cron`.
The container flags are used with `ecs deploy` only.


Ignore capacity issues
======================
If your cluster is undersized or the service's deployment options are not optimally set, the cluster
might be incapable to run blue-green-deployments. In this case, you might see errors like these:

    ERROR: (service my-service) was unable to place a task because no container instance met all of
    its requirements. The closest matching (container-instance 123456-1234-1234-1234-1234567890) is
    already using a port required by your task. For more information, see the Troubleshooting
    section of the Amazon ECS Developer Guide.

There might also be warnings about insufficient memory or CPU.

To ignore these warnings, you can run the deployment with the flag ``--ignore-warnings``::

    $ ecs deploy my-cluster my-service --ignore-warnings

In that case, the warning is printed, but the script continues and waits for a successful
deployment until it times out.

Deployment timeout
==================
The deploy and scale actions allow defining a timeout (in seconds) via the ``--timeout`` parameter.
This instructs ecs-deploy to wait for ECS to finish the deployment for the given number of seconds.

To run a deployment without waiting for the successful or failed result at all, set ``--timeout`` to the value of ``-1``.


Multi-Account Setup
===================
If you manage different environments of your system in multiple differnt AWS accounts, you can now easily assume a
deployment role in the target account in which your ECS cluster is running. You only need to provide ``--account``
with the AWS account id and ``--assume-role`` with the name of the role you want to assume in the target account.
ecs-deploy automatically assumes this role and deploys inside your target account:

Example::

    $ ecs deploy my-cluster my-service --account 1234567890 --assume-role ecsDeployRole




Scaling
-------

Scale a service
===============
To change the number of running tasks and scale a service up and down, run this command::

    $ ecs scale my-cluster my-service 4


Running a Task
--------------

Run a one-off task
==================
To run a one-off task, based on an existing task-definition, run this command::

    $ ecs run my-cluster my-task

You can define just the task family (e.g. ``my-task``) or you can run a specific revision of the task-definition (e.g.
``my-task:123``). And optionally you can add or adjust environment variables like this::

    $ ecs run my-cluster my-task:123 -e my-container MY_VARIABLE "my value"


Run a task with a custom command
================================

You can override the command definition via option ``-c`` or ``--command`` followed by the container name and the
command in a natural syntax, e.g. no conversion to comma-separation required::

    $ ecs run my-cluster my-task -c my-container "python some-script.py param1 param2"

The JSON syntax explained above regarding modifying a command is also applicable here.


Run a task in a Fargate Cluster
===============================

If you want to run a one-off task in a Fargate cluster, additional configuration is required, to instruct AWS e.g. which
subnets or security groups to use. The required parameters for this are:

- launchtype
- securitygroup
- subnet
- public-ip

Example::

    $ ecs run my-fargate-cluster my-task --launchtype=FARGATE --securitygroup sg-01234567890123456 --subnet subnet-01234567890123456 --public-ip

You can pass multiple ``subnet`` as well as multiple ``securitygroup`` values. the ``public-ip`` flag determines, if the task receives a public IP address or not.
Please see ``ecs run --help`` for more details.


Monitoring
----------
With ECS deploy you can track your deployments automatically. Currently only New Relic is supported:

New Relic
=========
To record a deployment in New Relic, you can provide the the API Key (**Attention**: this is a specific REST API Key, not the license key) and the application id in two ways:

Via cli options::

    $ ecs deploy my-cluster my-service --newrelic-apikey ABCDEFGHIJKLMN --newrelic-appid 1234567890

Or implicitly via environment variables ``NEW_RELIC_API_KEY`` and ``NEW_RELIC_APP_ID`` ::

    $ export NEW_RELIC_API_KEY=ABCDEFGHIJKLMN
    $ export NEW_RELIC_APP_ID=1234567890
    $ ecs deploy my-cluster my-service

Optionally you can provide additional information for the deployment:

- ``--comment "New feature X"`` - comment to the deployment
- ``--user john.doe`` - the name of the user who deployed with
- ``--newrelic-revision 1.0.0`` - explicitly set the revision to use for the deployment

Note: If neither ``--tag`` nor ``--newrelic-revision`` are provided, the deployment will not be recorded.


Troubleshooting
---------------
If the service configuration in ECS is not optimally set, you might be seeing
timeout or other errors during the deployment.

Timeout
=======
The timeout error means, that AWS ECS takes longer for the full deployment cycle then ecs-deploy is told to wait. The deployment itself still might finish successfully, if there are no other problems with the deployed containers.

You can increase the time (in seconds) to wait for finishing the deployment via the ``--timeout`` parameter. This time includes the full cycle of stopping all old containers and (re)starting all new containers. Different stacks require different timeout values, the default is 300 seconds.

The overall deployment time depends on different things:

- the type of the application. For example node.js containers tend to take a long time to get stopped. But nginx containers tend to stop immediately, etc.
- are old and new containers able to run in parallel (e.g. using dynamic ports)?
- the deployment options and strategy (Maximum percent > 100)?
- the desired count of running tasks, compared to
- the number of ECS instances in the cluster


Alternative Implementation
--------------------------
There are some other libraries/tools available on GitHub, which also handle the deployment of containers in AWS ECS. If you prefer another language over Python, have a look at these projects:

Shell
  ecs-deploy - https://github.com/silinternational/ecs-deploy

Ruby
  broadside - https://github.com/lumoslabs/broadside
