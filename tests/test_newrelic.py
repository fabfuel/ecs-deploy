from pytest import fixture, raises
from mock import patch

from ecs_deploy.newrelic import Deployment, NewRelicDeploymentException


class DeploymentResponseSuccessfulMock(object):
    status_code = 201
    content = {
        "deployment": {
            "id": 1234567890,
            "revision": "1.2.3",
            "changelog": "Lorem Ipsum",
            "description": "Lorem ipsum usu amet dicat nullam ea. Nec detracto lucilius democritum in.",
            "user": "username", "timestamp": "2016-06-21T09:45:08+00:00",
            "links": {"application": 12345}
        },
        "links": {"deployment.agent": "/v2/applications/{application_id}"}
    }


class DeploymentResponseUnsuccessfulMock(object):
    status_code = 400
    content = {"message": "Something went wrong"}


@fixture
def api_key():
    return 'APIKEY'


@fixture
def app_id():
    return '12345'


@fixture
def user():
    return 'username'


@fixture
def revision():
    return '1.2.3'


@fixture
def changelog():
    return 'Lorem Ipsum'


@fixture
def description():
    return 'Lorem ipsum usu amet dicat nullam ea. Nec detracto lucilius democritum in.'


def test_get_endpoint(api_key, app_id, user):
    endpoint = 'https://api.newrelic.com/v2/applications/%(app_id)s/deployments.json' % dict(app_id=app_id)
    deployment = Deployment(api_key, app_id, user)
    assert deployment.endpoint == endpoint


def test_get_headers(api_key, app_id, user):
    headers = {
        'X-Api-Key': api_key,
        'Content-Type': 'application/json',
    }

    deployment = Deployment(api_key, app_id, user)
    assert deployment.headers == headers


def test_get_payload(api_key, app_id, user, revision, changelog, description):
    payload = {
        'deployment': {
            'revision': revision,
            'changelog': changelog,
            'description': description,
            'user': user,
        }
    }
    deployment = Deployment(api_key, app_id, user)
    assert deployment.get_payload(revision, changelog, description) == payload


@patch('requests.post')
def test_deploy_sucessful(post, api_key, app_id, user, revision, changelog, description):
    post.return_value = DeploymentResponseSuccessfulMock()

    deployment = Deployment(api_key, app_id, user)
    response = deployment.deploy(revision, changelog, description)
    payload = deployment.get_payload(revision, changelog, description)

    post.assert_called_with(deployment.endpoint, headers=deployment.headers, json=payload)
    assert response.status_code == 201


@patch('requests.post')
def test_deploy_unsucessful(post, api_key, app_id, user, revision, changelog, description):
    with raises(NewRelicDeploymentException):
        post.return_value = DeploymentResponseUnsuccessfulMock()
        deployment = Deployment(api_key, app_id, user)
        deployment.deploy(revision, changelog, description)
