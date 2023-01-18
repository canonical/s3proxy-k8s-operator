# Copyright 2022 Canonical
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import ops.testing
from ops.model import ActiveStatus, WaitingStatus
from ops.testing import Harness

from charm import S3ProxyK8SOperatorCharm

ops.testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    @patch("lightkube.core.client.GenericSyncClient")
    def setUp(self, *_):
        self.container_name: str = "mimir"
        self.harness = Harness(S3ProxyK8SOperatorCharm)
        patcher = patch.object(S3ProxyK8SOperatorCharm, "_workload_version", new_callable=PropertyMock)
        self.mock_version = patcher.start()
        self.mock_version.return_value = "2.0.0"
        self.addCleanup(patcher.stop)
        self.harness.begin()

    def test_pebble_ready_with_anonymous_access(self):
        self.harness.update_config(
            {
                "identity": "unittestid",
                "credential": "unittestcredential"
            }
        )

        expected_plan = {
            "services": {
                "s3proxy": {
                    "override": "replace",
                    "summary": "s3proxy daemon",
                    "command": 'java -DLOG_LEVEL="info" '
                               '-Djclouds.region="us-east-1" '
                               '-Djclouds.provider="filesystem" '
                               '-Djclouds.identity="remote-identity" '
                               '-Djclouds.filesystem.basedir="/data/blobstore" '
                               '-Ds3proxy.authorization="none" '
                               '-Ds3proxy.identity="unittestid" '
                               '-Ds3proxy.credential="unittestcredential" '
                               '-Ds3proxy.cors-allow-all="true" '
                               '-Ds3proxy.endpoint="http://0.0.0.0:8080" '
                               '-jar /usr/bin/s3proxy --properties '
                               '/dev/null',
                    "startup": "enabled",
                }
            },
        }

        self.harness.container_pebble_ready("s3proxy")
        updated_plan = self.harness.get_container_pebble_plan("s3proxy").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("s3proxy").get_service("s3proxy")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_pebble_ready_with_authentication_access(self):
        self.harness.update_config(
            {
                "identity": "unittestid",
                "credential": "unittestcredential",
                "authorization": "aws-v2-or-v4"
            }
        )

        expected_plan = {
            "services": {
                "s3proxy": {
                    "override": "replace",
                    "summary": "s3proxy daemon",
                    "command": 'java -DLOG_LEVEL="info" '
                               '-Djclouds.region="us-east-1" '
                               '-Djclouds.provider="filesystem" '
                               '-Djclouds.identity="remote-identity" '
                               '-Djclouds.filesystem.basedir="/data/blobstore" '
                               '-Ds3proxy.authorization="aws-v2-or-v4" '
                               '-Ds3proxy.identity="unittestid" '
                               '-Ds3proxy.credential="unittestcredential" '
                               '-Ds3proxy.cors-allow-all="true" '
                               '-Ds3proxy.endpoint="http://0.0.0.0:8080" '
                               '-jar /usr/bin/s3proxy --properties '
                               '/dev/null',
                    "startup": "enabled",
                }
            },
        }

        self.harness.container_pebble_ready("s3proxy")
        updated_plan = self.harness.get_container_pebble_plan("s3proxy").to_dict()
        self.assertEqual(expected_plan, updated_plan)
        service = self.harness.model.unit.get_container("s3proxy").get_service("s3proxy")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_config_changed_cannot_connect_sets_waiting_status(self):
        ops.testing.SIMULATE_CAN_CONNECT = False
        self.harness.update_config({"cpu": "256"})
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for Pebble ready"))

    def test_action_handler_returns_credentials(self):
        self.harness.update_config(
            {
                "identity": "unittestid",
                "credential": "unittestcredential",
                "authorization": "aws-v2-or-v4"
            }
        )

        event = MagicMock()
        self.harness.charm._on_get_credentials(event)
        event.set_results.assert_called_with(
            {
                "identity": "unittestid",
                "credential": "unittestcredential"
            }
        )