#!/usr/bin/env python3
# Copyright 2021 Syed Mohammad Adnan Karim
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus
from ops.pebble import ConnectionError

logger = logging.getLogger(__name__)


class FluentdOperatorCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.elasticsearch_relation_changed, self._on_elasticsearch_relation_changed)
        self.framework.observe(self.on.elasticsearch_relation_broken, self._on_elasticsearch_relation_broken)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self._stored.set_default(data={
            "fluentConfig": """
                <source>
                    @type forward
                    port 24224
                </source>

                <source>
                    @type http
                    port 9880
                </source>

                <match *.**>
                    @type copy

                    <store>
                        @type stdout
                    </store>
                </match>
            """
        })

    def restartContainerService(self, container, service):
        # Stop the service if it is already running
        if container.get_service(service).is_running():
            container.stop(service)
        # Restart it and report a new status to Juju
        container.start(service)
        logging.info("Restarted {0} service".format(service))
    
    def addSectionToFluentConf(self, fluentConfig, insertionPoint, newSection):
        oldFluentConfig = fluentConfig.split(insertionPoint)
        newFluentConfig = oldFluentConfig[0] + insertionPoint + newSection + oldFluentConfig[1]
        return newFluentConfig

    def removeSectionFromFluentConf(self, fluentConfig, sectionToRemove):
        newFluentConfig = fluentConfig.split(sectionToRemove)
        fluentConfig = newFluentConfig[0] + newFluentConfig[1]

    def _on_config_changed(self, event):
        """Handle the config changed event."""
        # Get a reference to the container so we can manipulate it
        container = self.unit.get_container("fluentd")
        # Create a new config layer - specify 'override: merge' in the 'fluentd'
        # service definition to overlay with existing layer
        layer = {
            "summary": "fluentd layer",
            "description": "pebble config layer for fluent/fluentd",
            "services": {
                "fluentd": {
                    "override": "replace",
                    "summary": "fluentd service",
                    "command": "tini -s -- /bin/entrypoint.sh fluentd",
                    "startup": "enabled",
                    # "environment": {
                    #                 "FLUENT_ELASTICSEARCH_HOST": self.model.config["elasticsearch-hostname"],
                    #                 "FLUENT_ELASTICSEARCH_PORT": self.model.config["elasticsearch-port"],
                    #                 # "FLUENT_ELASTICSEARCH_HOST": self._stored.data['host'],
                    #                 # "FLUENT_ELASTICSEARCH_PORT": self._stored.data['port'],
                    #                },
                }
            },
        }
        try:
            # Get the current config
            services = container.get_plan().to_dict().get("services", {})
        except ConnectionError:
            # Since this is a config-changed handler and that hook can execute
            # before pebble is ready, we may get a connection error here. Let's
            # defer the event, meaning it will be retried the next time any
            # hook is executed. This method will be rerun when that condition
            #  is met (because of `event.defer()`), and so the `get_container` 
            # call will succeed and we'll continue to the subsequent steps.
            event.defer()
            return
        # Check if there are any changes to services
        if services != layer["services"]:
            # Changes were made, add the new layer
            container.add_layer("fluentd", layer, combine=True)
            logging.info("Added updated layer 'fluentd' to Pebble plan")
            self.restartContainerService(container=container, service="fluentd")
        # All is well, set an ActiveStatus
        self.unit.status = ActiveStatus()

    def _on_elasticsearch_relation_changed(self, event) -> None:
        # Check if the remote unit has set the 'port' field in the
        # application data bucket
        host = event.relation.data[event.unit].get("private-address")
        port = event.relation.data[event.unit].get("port")
        logging.info("Elasticsearch Host: {0}".format(host))
        logging.info("Elasticsearch Port: {0}".format(port))
        if host == None or port == None:
            # Elasticsearch relation data not fully populated yet
            return

        container = self.unit.get_container("fluentd")
        fluentConfig = container.pull('/fluentd/etc/fluent.conf').read()
        logging.info("Current fluent.conf:\n{0}".format(fluentConfig))
        elasticsearchOutputConfig = """
        <store>
            @type elasticsearch
            host {0}
            port {1}
            logstash_format true
            logstash_prefix fluentd
            logstash_dateformat %Y%m%d
            include_tag_key true
            type_name access_log
            tag_key @log_name
            flush_interval 1s
        </store>""".format(host, port)
        logging.info(elasticsearchOutputConfig)
        if fluentConfig.find(elasticsearchOutputConfig) == -1:
            newFluentConfig = self.addSectionToFluentConf(
                fluentConfig=fluentConfig, 
                insertionPoint="@type copy", 
                newSection=elasticsearchOutputConfig
            )
            self._stored.data['elasticsearchOutputConfig'] = elasticsearchOutputConfig
            self._stored.data['fluentConfig'] = newFluentConfig
            logging.info("New fluent.conf:\n{0}".format(newFluentConfig))
            container.push('/fluentd/etc/fluent.conf', newFluentConfig, make_dirs=True)
            self.restartContainerService(container=container, service="fluentd")

        self._on_config_changed(event)

    def _on_elasticsearch_relation_broken(self, event) -> None:
        logging.info("Cleanup elasticsearch config")
        elasticsearchOutputConfig = self._stored.data['elasticsearchOutputConfig']

        container = self.unit.get_container("fluentd")
        fluentConfig = container.pull('/fluentd/etc/fluent.conf').read()
        fluentConfig = fluentConfig.replace(elasticsearchOutputConfig, "")
        self._stored.data['fluentConfig'] = fluentConfig
        self._stored.data.pop('elasticsearchOutputConfig', None)
        container.push('/fluentd/etc/fluent.conf', fluentConfig, make_dirs=True)

        self.restartContainerService(container=container, service="fluentd")

    def _on_update_status(self, event) -> None:
        container = self.unit.get_container("fluentd")
        fluentConfig = container.pull('/fluentd/etc/fluent.conf').read()
        logging.info(fluentConfig)
        logging.info(self._stored.data)

if __name__ == "__main__":
    main(FluentdOperatorCharm)
