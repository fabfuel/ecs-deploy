from copy import deepcopy

from freezegun import freeze_time
from pytest import fixture, raises
from mock import patch

from ecs_deploy.ecs import EcsTaskDefinition
from ecs_deploy.slack import SlackNotification, SlackException
from tests.test_ecs import PAYLOAD_TASK_DEFINITION_1


class NotifyResponseSuccessfulMock(object):
    status_code = 200


class NotifyResponseUnsuccessfulMock(object):
    status_code = 400
    content = {"message": "Something went wrong"}


@fixture
def url():
    return 'https://slack.test'


@fixture
def service_match():
    return '.*'


@fixture
def task_definition():
    return EcsTaskDefinition(**deepcopy(PAYLOAD_TASK_DEFINITION_1))


def test_get_payload_without_messages(url, service_match):
    slack = SlackNotification(url, service_match)

    payload = slack.get_payload('Foobar', [], 'good')

    expected = {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'color': 'good',
                'pretext': 'Foobar',
                'fields': [],
            }
        ],
    }

    assert payload == expected


def test_get_payload_with_messages(url, service_match):
    slack = SlackNotification(url, service_match)

    messages = (
        ('foo', 'bar'),
        ('lorem', 'ipsum'),
    )

    payload = slack.get_payload('Foobar', messages, 'good')

    expected = {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'color': 'good',
                'pretext': 'Foobar',
                'fields': [
                    {'short': True, 'title': 'foo', 'value': 'bar'},
                    {'short': True, 'title': 'lorem', 'value': 'ipsum'}
                ],
            }
        ],
    }

    assert payload == expected


@patch('requests.post')
def test_notify_start_without_url(post_mock, url, service_match, task_definition):
    slack = SlackNotification(None, None)
    slack.notify_start('my-cluster', 'my-tag', task_definition, 'my-comment', 'my-user', 'my-service', 'my-rule')

    post_mock.assert_not_called()


@patch('requests.post')
def test_notify_start(post_mock, url, service_match, task_definition):
    post_mock.return_value = NotifyResponseSuccessfulMock()

    task_definition.set_images(webserver=u'new-image:my-tag', application=u'app-image:another-tag')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))

    slack = SlackNotification(url, service_match)
    slack.notify_start('my-cluster', 'my-tag', task_definition, 'my-comment', 'my-user', 'my-service', 'my-rule')

    payload = {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'pretext': 'Deployment has started',
                'color': None,
                'fields': [
                    {'title': 'Cluster', 'value': 'my-cluster', 'short': True},
                    {'title': 'Service', 'value': 'my-service', 'short': True},
                    {'title': 'Scheduled Task', 'value': 'my-rule', 'short': True},
                    {'title': 'Tag', 'value': 'my-tag', 'short': True},
                    {'title': 'User', 'value': 'my-user', 'short': True},
                    {'title': 'Comment', 'value': 'my-comment', 'short': True},
                    {'title': 'image', 'value': 'app-image:another-tag', 'short': True},
                    {'title': 'Environment', 'value': '_sensitive (therefore hidden)_', 'short': True}
                ]
            }
        ]
    }

    post_mock.assert_called_with(url, json=payload)


@patch('requests.post')
def test_notify_start_without_tag(post_mock, url, service_match, task_definition):
    post_mock.return_value = NotifyResponseSuccessfulMock()

    task_definition.set_images(webserver=u'new-image:my-tag', application=u'app-image:another-tag')
    task_definition.set_environment((('webserver', 'foo', 'baz'),))

    slack = SlackNotification(url, service_match)
    slack.notify_start('my-cluster', None, task_definition, 'my-comment', 'my-user', 'my-service', 'my-rule')

    payload = {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'pretext': 'Deployment has started',
                'color': None,
                'fields': [
                    {'title': 'Cluster', 'value': 'my-cluster', 'short': True},
                    {'title': 'Service', 'value': 'my-service', 'short': True},
                    {'title': 'Scheduled Task', 'value': 'my-rule', 'short': True},
                    {'title': 'User', 'value': 'my-user', 'short': True},
                    {'title': 'Comment', 'value': 'my-comment', 'short': True},
                    {'title': 'image', 'value': 'new-image:my-tag', 'short': True},
                    {'title': 'image', 'value': 'app-image:another-tag', 'short': True},
                    {'title': 'Environment', 'value': '_sensitive (therefore hidden)_', 'short': True}
                ]
            }
        ]
    }

    post_mock.assert_called_with(url, json=payload)


@patch('requests.post')
@freeze_time()
def test_notify_success(post_mock, url, service_match, task_definition):
    post_mock.return_value = NotifyResponseSuccessfulMock()

    slack = SlackNotification(url, service_match)
    slack.notify_success('my-cluster', 'my-tag', 'my-service', 'my-rule')

    payload =  {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'pretext': 'Deployment finished successfully',
                'color': 'good',
                'fields': [
                    {'title': 'Cluster', 'value': 'my-cluster', 'short': True},
                    {'title': 'Service', 'value': 'my-service', 'short': True},
                    {'title': 'Scheduled Task', 'value': 'my-rule', 'short': True},
                    {'title': 'Revision', 'value': 'my-tag', 'short': True},
                    {'title': 'Duration', 'value': '0:00:00', 'short': True}
                ]
            }
        ]
    }

    post_mock.assert_called_with(url, json=payload)


@patch('requests.post')
@freeze_time()
def test_notify_success(post_mock, url, service_match, task_definition):
    post_mock.return_value = NotifyResponseSuccessfulMock()

    slack = SlackNotification(url, service_match)
    slack.notify_failure('my-cluster', 'my-error', 'my-service', 'my-rule')

    payload =  {
        'username': 'ECS Deploy',
        'attachments': [
            {
                'pretext': 'Deployment failed',
                'color': 'danger',
                'fields': [
                    {'title': 'Cluster', 'value': 'my-cluster', 'short': True},
                    {'title': 'Service', 'value': 'my-service', 'short': True},
                    {'title': 'Scheduled Task', 'value': 'my-rule', 'short': True},
                    {'title': 'Duration', 'value': '0:00:00', 'short': True},
                    {'title': 'Error', 'value': 'my-error', 'short': True},
                ]
            }
        ]
    }

    post_mock.assert_called_with(url, json=payload)


@patch('requests.post')
def test_notify_start_without_url(post_mock, url, service_match, task_definition):
    slack = SlackNotification(None, None)
    slack.notify_start('my-cluster', 'my-tag', task_definition, 'my-comment', 'my-user', 'my-service', 'my-rule')
    post_mock.assert_not_called()


@patch('requests.post')
def test_notify_success_without_url(post_mock, url, service_match, task_definition):
    slack = SlackNotification(None, None)
    slack.notify_success('my-cluster', 13, 'my-service', 'my-rule')
    post_mock.assert_not_called()


@patch('requests.post')
def test_notify_failure_without_url(post_mock, url, service_match, task_definition):
    slack = SlackNotification(None, None)
    slack.notify_failure('my-cluster', 'my-error', 'my-service', 'my-rule')
    post_mock.assert_not_called()



@patch('requests.post')
def test_notify_start_failed(post, url, service_match, task_definition):
    with raises(SlackException):
        post.return_value = NotifyResponseUnsuccessfulMock()
        slack = SlackNotification(url, service_match)
        slack.notify_start('my-cluster', 'my-tag', task_definition, 'my-comment', 'my-user', 'my-service', 'my-rule')


@patch('requests.post')
def test_notify_success_failed(post, url, service_match, task_definition):
    with raises(SlackException):
        post.return_value = NotifyResponseUnsuccessfulMock()
        slack = SlackNotification(url, service_match)
        slack.notify_success('my-cluster', 'my-tag', 'my-service', 'my-rule')


@patch('requests.post')
def test_notify_failure_failed(post, url, service_match, task_definition):
    with raises(SlackException):
        post.return_value = NotifyResponseUnsuccessfulMock()
        slack = SlackNotification(url, service_match)
        slack.notify_failure('my-cluster', 'my-error', 'my-service', 'my-rule')
