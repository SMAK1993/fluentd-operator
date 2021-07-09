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
        # self.framework.observe(self.on.fortune_action, self._on_fortune_action)
        self._stored.set_default(things=[])

    def _on_config_changed(self, event):
        """Handle the config changed event."""
        # return
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
                    # "command": "/bin/entrypoint.sh",
                    "command": "tini -- /fluentd/entrypoint.sh",
                    "startup": "enabled",
                    "environment": {"FLUENT_ELASTICSEARCH_HOST": self.model.config["elasticsearch-hostname"],
                                    "FLUENT_ELASTICSEARCH_PORT": self.model.config["elasticsearch-port"],
                                    "FLUENT_ELASTICSEARCH_SSL_VERIFY": "false",
                                    "FLUENTD_SYSTEMD_CONF": "disable"
                                   },
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
            # Stop the service if it is already running
            if container.get_service("fluentd").is_running():
                container.stop("fluentd")
            # Restart it and report a new status to Juju
            container.start("fluentd")
            logging.info("Restarted fluentd service")
        # All is well, set an ActiveStatus
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(FluentdOperatorCharm)
