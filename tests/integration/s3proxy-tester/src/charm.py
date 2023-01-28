#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""A Charm to functionally test the s3proxy Operator."""

import logging
from pathlib import Path

from boto3 import client
from charms.s3proxy_k8s.v0.object_storage import ObjectStorageRequirer
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)


class S3ProxyTesterCharm(CharmBase):
    """A Charm used to test the Grafana charm."""

    def __init__(self, *args):
        super().__init__(*args)
        self._name = "s3proxy-tester"
        self.object_storage = ObjectStorageRequirer(self, bucket="s3proxy-tester")
        self.framework.observe(self.object_storage.on.ready, self.on_storage_ready)

        self.framework.observe(
            self.on.s3proxy_tester_pebble_ready, self._on_s3proxy_tester_pebble_ready
        )

        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_s3proxy_tester_pebble_ready(self, _):
        """Just set it ready. It's a pause image."""
        self.unit.status = ActiveStatus()

    def _on_config_changed(self, _):
        """Reconfigure the s3proxy tester."""
        container = self.unit.get_container(self._name)
        if not container.can_connect():
            self.unit.status = BlockedStatus("Waiting for Pebble ready")
            return

        self.unit.status = ActiveStatus()

    def on_storage_ready(self, event):
        """Create some test data in s3."""
        s3client = client(
            service_name="s3",
            endpoint_url=event.endpoint,
            aws_access_key_id=event.access_key,
            aws_secret_access_key=event.secret_key,
        )
        _ = Path("./s3proxy-tester.txt").write_text("some test data")
        s3client.upload_file(
            Bucket=event.bucket, Filename="./s3proxy-tester.txt", Key="s3proxy-tester.txt"
        )


if __name__ == "__main__":
    main(S3ProxyTesterCharm)
