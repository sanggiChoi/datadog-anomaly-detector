import os
import slackweb
import configparser
from functools import partial
from datadog import initialize, api

from logging import getLogger
logger = getLogger('ChangeFinder')


class DatadogAPIHelper:

    def __init__(self, app_key, api_key, does_notify_slack=True):
        initialize(app_key=app_key, api_key=api_key)

        self.does_notify_slack = does_notify_slack

        # slack notification setting
        if does_notify_slack:
            self.load_slack_config()

    def load_slack_config(self):
        parser = configparser.ConfigParser()
        parser.read(os.getcwd() + '/config/datadog.ini')

        if 'slack' not in parser:
            logger.warning('Datadog: Slack notification setting is true, but the configuration cannot be found from the .ini file.')
            self.does_notify_slack = False
            return

        s = parser['slack']
        self.slack = slackweb.Slack(url=s.get('url'))

        channel = s.get('channel') or '#general'
        username = s.get('username') or 'Bot'
        icon_emoji = s.get('icon_emoji') or ':ghost:'

        self.slack_notify = partial(self.slack.notify,
                                    channel=channel,
                                    username=username,
                                    icon_emoji=icon_emoji)

    def get_series(self, start, end, query):
        """Get time series points.

        Args:
            start (int): Unix timestamp.
            end (int): Unix timestamp.
            query (string): Datadog query.

        """
        j = api.Metric.query(start=start, end=end, query=query)

        if 'errors' in j:
            msg = 'Datadog: %s' % j['errors']
            self.slack_notify(attachments=[{'text': msg, 'color': 'danger'}])
            raise RuntimeError(msg)
        if 'status' in j and j['status'] != 'ok':
            msg = 'Datadog: API status was NOT ok: %s' % j['status']
            self.slack_notify(attachments=[{'text': msg, 'color': 'danger'}])
            raise RuntimeError(msg)

        series = []

        for d in j['series']:
            # p = [ timestamp, value ]
            series += [{'src_metric': d['metric'],
                        'scope': d['scope'],
                        'time': int(p[0]),
                        'raw_value': p[1]
                        } for p in d['pointlist']]

        return sorted(series, key=lambda d: d['time'])

    def post_metric(self, metric, points, host):
        """Post the given points to a specified metric with host information.

        Args:
            metric (str): Destination metric name.
            points (one of belows):
                p value
                (p time, p value)
                [(p_1 time, p_1 value), ..., (p_n time, p_n value)]
            host: Metric source.

        """
        api.Metric.send(metric=metric, points=points, host=host)