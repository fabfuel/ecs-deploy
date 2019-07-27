import requests


class NewRelicException(Exception):
    pass


class NewRelicDeploymentException(NewRelicException):
    pass


class Deployment(object):
    API_HOST_US = 'api.newrelic.com'
    API_HOST_EU = 'api.eu.newrelic.com'
    ENDPOINT = 'https://%(host)s/v2/applications/%(app_id)s/deployments.json'

    def __init__(self, api_key, app_id, user, region):
        self.__api_key = api_key
        self.__app_id = app_id
        self.__user = user
        self.__region = region.lower() if region else 'us'

    @property
    def endpoint(self):
        if self.__region == 'eu':
            host = self.API_HOST_EU
        else:
            host = self.API_HOST_US
        return self.ENDPOINT % dict(host=host, app_id=self.__app_id)

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
