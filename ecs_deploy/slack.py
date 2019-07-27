import re
from datetime import datetime
from requests import post


class SlackException(Exception):
    pass


class SlackNotification(object):
    def __init__(self, url, service_match):
        self.__url = url
        self.__service_match_re = re.compile(service_match)
        self.__timestamp_start = None

    def get_payload(self, title, messages, color=None):
        fields = []
        for message in messages:
            field = {
                'title': message[0],
                'value': message[1],
                'short': True
            }
            fields.append(field)

        payload = {
            "username": "ECS Deploy",
            "attachments": [
                {
                    "pretext": title,
                    "color": color,
                    "fields": fields
                }
            ]
        }

        return payload

    def notifiy_start(self, cluster, tag, task_definition, comment, user, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        self.__timestamp_start = datetime.utcnow()

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))

        if rule:
            messages.append(('Scheduled Task', rule))

        if tag:
            messages.append(('Tag', tag))

        if user:
            messages.append(('User', user))

        if comment:
            messages.append(('Comment', comment))

        for diff in task_definition.diff:
            if diff.field == 'image' and diff.value.endswith(':' + tag):
                continue
            if diff.field == 'environment':
                messages.append(('Environment', '_sensitive (therefore hidden)_'))
                continue

            messages.append((diff.field, diff.value))

        payload = self.get_payload('Deployment has started', messages)


        response = post(self.__url, json=payload)

        response.raise_for_status()

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

        return response

    def notify_success(self, cluster, revision, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        duration = datetime.utcnow() - self.__timestamp_start

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))
        if rule:
            messages.append(('Scheduled Task', rule))

        messages.append(('Revision', revision))
        messages.append(('Duration', str(duration)))

        payload = self.get_payload('Deployment finished successfully', messages, 'good')

        response = post(self.__url, json=payload)

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

        return response

    def notify_failure(self, cluster, error, service=None, rule=None):
        if not self.__url or not self.__service_match_re.search(service or rule):
            return

        duration = datetime.utcnow() - self.__timestamp_start

        messages = [
            ('Cluster', cluster),
        ]

        if service:
            messages.append(('Service', service))
        if rule:
            messages.append(('Scheduled Task', rule))

        messages.append(('Duration', str(duration)))
        messages.append(('Error', error))

        payload = self.get_payload('Deployment failed', messages, 'danger')

        response = post(self.__url, json=payload)

        if response.status_code != 200:
            raise SlackException('Notifying deployment failed')

        return response
