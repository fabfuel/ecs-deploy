ECS Deploy
----------

.. image:: https://travis-ci.org/fabfuel/ecs-deploy.svg?branch=develop
    :target: https://travis-ci.org/fabfuel/ecs-deploy

.. image:: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy/badges/coverage.png?b=develop
    :target: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy

.. image:: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy/badges/quality-score.png?b=develop
    :target: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy

`ecs-deploy` simplifies deployments on Amazon ECS by providing a convinience CLI tool for complex actions, which are executed pretty often.

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


Installation
------------

The project is availably on PyPI. Simply run::

    $ pip install ecs-deploy


Configuration
-------------
As **ecs-deploy** is based on boto3 (the official AWS Python library), there are several ways to configure and store the 
authentication credentials. Please read the boto3 documentation for more details 
(http://boto3.readthedocs.org/en/latest/guide/configuration.html#configuration). The simplest way is by running::

    $ aws configure

Alternatively you can pass the AWS credentials (via `--access-key-id` and `--secret-access-key`) or the AWS
configuration profile (via `--profile`) as options when you run `ecs`. 

Actions
-------
Currently the following actions are supported:

deploy
======
Redeploy a service either without any modifications or with a new image, environment variable and/or command definition.

scale
=====
Scale a service up or down and change the number of running tasks.

run
===
Run a one-off task based on an existing task-definition and optionally override command and/or environment variables.


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
To redeploy a service without any modifications, but pulling the most recent image versions, run the follwing command.
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


Modify a command
================
To change the command of a specific container, run the following command::

    $ ecs deploy my-cluster my-service --command webserver "nginx"

This will modify the **webserver** container and change its command to "nginx".


Set a task role
===============
To change or set the role, the service's task should run as, use the following command::

    $ ecs deploy my-cluster my-service -r arn:aws:iam::123456789012:role/MySpecialEcsTaskRole

This will set the task role to "MySpecialEcsTaskRole".

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

Optionally you can provide an additional comment to the deployment via ``--comment "New feature X"`` and the name of the user who deployed with ``--user john.doe``


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
