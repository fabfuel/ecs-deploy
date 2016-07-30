import requests


class NewRelicException(Exception):
    pass


class NewRelicDeploymentException(NewRelicException):
    pass


class Deployment(object):
    ENDPOINT = 'https://api.newrelic.com/v2/applications/%(app_id)s/deployments.json'

    def __init__(self, api_key, app_id, user):
        self.__api_key = api_key
        self.__app_id = app_id
        self.__user = user

    @property
    def endpoint(self):
        return self.ENDPOINT % dict(app_id=self.__app_id)

    @property
    def headers(self):
        return {
            'Content-Type': 'application/json',
            'X-Api-Key': self.__api_key
        }

    def get_payload(self, revision, changelog, description):
        return {
            "deployment" : {
                "revision": str(revision),
                "changelog": str(changelog),
                "description": str(description),
                "user": str(self.__user)
            }
        }

    def deploy(self, revision, changelog, description):
        payload = self.get_payload(revision, changelog, description)
        response = requests.post(self.endpoint, headers=self.headers, json=payload)

        if response.status_code != 201:
            try:
                raise NewRelicDeploymentException('Recording deployment failed: %s' %
                                                  response.json()['error']['title'])
            except (AttributeError, KeyError):
                raise NewRelicDeploymentException('Recording deployment failed')

        return response
