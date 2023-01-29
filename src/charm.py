#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju Charmed Operator for s3proxy."""

import logging
import re
import secrets
import socket
import string
from dataclasses import dataclass, fields
from typing import Any, Dict, Literal, Optional

import boto3
from boto3 import resource as s3client
from botocore import exceptions
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.s3proxy_k8s.v0.object_storage import (
    ObjectStorageDataProvidedEvent,
    ObjectStorageDataRefreshEvent,
    SingleAuthObjectStorageProvider,
)
from ops.charm import ActionEvent, CharmBase, HookEvent, WorkloadEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, WaitingStatus
from ops.pebble import Layer

DATA_DIR = "/data"
logger = logging.getLogger(__name__)


@dataclass
class S3ProxyConfig:
    """A basic holder and transformer for S3Proxy Configuration."""

    authorization: Literal["aws-v2-or-v4", "none"] = "none"
    identity: str = ""
    credential: str = ""
    cors_allow_all: bool = True
    endpoint: str = "http://0.0.0.0:8080"

    def as_args(self) -> Dict[str, Any]:
        """Return as substituted environment variables."""
        env = dict(
            (f"s3proxy.{re.sub(r'_', '-', field.name)}", getattr(self, field.name))
            for field in fields(self)
        )
        env["s3proxy.cors-allow-all"] = str(env["s3proxy.cors-allow-all"]).lower()
        return env

    @classmethod
    def from_dict(cls, obj):
        """Build an object from a dict."""
        return cls(**obj)


class S3ProxyK8SOperatorCharm(CharmBase):
    """A Juju Charmed Operator for S3Proxy."""

    name = "s3proxy"
    http_listen_port = 8080
    instance_addr = "127.0.0.1"

    # TODO: Move to Secrets when released
    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._container = self.unit.get_container(self.name)

        # TODO: Move to Secrets when released
        self._stored.set_default(  # type: ignore
            identity="",
            credential="",
        )

        self.service_patch = KubernetesServicePatch(self, [(self.app.name, self.http_listen_port)])

        self.object_storage = SingleAuthObjectStorageProvider(self, "s3")
        self.framework.observe(self.object_storage.on.requested, self._on_client_requested)
        self.framework.observe(self.object_storage.on.refresh, self._on_refresh_endpoint)
        self.framework.observe(self.on.get_credentials_action, self._on_get_credentials)  # type: ignore

        self.framework.observe(self.on.s3proxy_pebble_ready, self._on_s3proxy_pebble_ready)  # type: ignore
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    @property
    def _credentials(self) -> Dict[str, Any]:
        """Generate credentials if they don't exist and aren't set in config."""
        alphabet = string.ascii_letters + string.digits

        identity = self.config.get("identity", "") or self._stored.identity  # type: ignore
        credential = self.config.get("credential", "").lower() or self._stored.credential  # type: ignore

        if not identity:
            # The AWS default for access key length is 20 characters
            identity = "".join(secrets.choice(alphabet) for i in range(20))

        if not credential:
            # The AWS default for access key length is 40 characters
            credential = "".join(secrets.choice(alphabet) for i in range(40))

        self._stored.identity = identity or ""  # type: ignore
        self._stored.credential = credential  # type: ignore

        return {"identity": identity, "credential": credential}

    def _on_get_credentials(self, event: ActionEvent) -> None:
        """Return the connection credentials."""
        cred = self._credentials
        event.set_results({"identity": cred["identity"], "credential": cred["credential"]})

    @property
    def _config(self) -> S3ProxyConfig:
        """Generate an S3ProxyConfig from model config and defaults."""
        cfg = dict(self.model.config)
        cfg.update(self._credentials)
        return S3ProxyConfig.from_dict(cfg)

    def _on_s3proxy_pebble_ready(self, event: WorkloadEvent):
        self._set_s3proxy_version()
        self._configure()

    def _on_config_changed(self, event: HookEvent):
        self._configure()

    def _on_refresh_endpoint(self, event: ObjectStorageDataRefreshEvent):
        """Update observer endpoints with a new URI."""
        self.object_storage.update_endpoints(
            {
                "endpoint": f"http://{self.hostname}:{self.http_listen_port}",
            }
        )

    def _on_client_requested(self, event: ObjectStorageDataProvidedEvent):
        """Update requirers with endpoint information."""
        if not self._container.can_connect() or not self.is_ready:
            event.defer()
            return

        client = s3client(
            service_name="s3",
            endpoint_url="http://127.0.0.1:8080",
            aws_access_key_id=self._credentials["identity"],
            aws_secret_access_key=self._credentials["credential"],
        )

        try:
            client.create_bucket(Bucket=event.bucket)
        except (
            client.meta.client.exceptions.BucketAlreadyExists,
            client.meta.client.exceptions.BucketAlreadyOwnedByYou,
        ) as e:
            logger.debug("Bucket already exists: %r", e)

        self.object_storage.update_endpoints(
            {
                "endpoint": f"http://{self.hostname}:{self.http_listen_port}",
                "access-key": self._credentials["identity"],
                "secret-key": self._credentials["credential"],
            },
            event.relation.id,
        )

    def _configure(self):
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for Pebble ready")
            return

        if self._container.get_plan().services != self._build_layer().services:
            self._container.add_layer(self.name, self._build_layer(), combine=True)
            self._container.replan()
            logger.info("s3proxy (re)started")

        self.unit.status = ActiveStatus()

    def _build_layer(self) -> Layer:
        args = {
            "LOG_LEVEL": "info",
            "jclouds.region": "us-east-1",
            "jclouds.provider": "filesystem",
            "jclouds.identity": "remote-identity",
            "jclouds.identity": "remote-identity",
            "jclouds.filesystem.basedir": f"{DATA_DIR}/blobstore",
        }
        args.update(self._config.as_args())
        arg_str = " ".join([f'-D{k}="{v}"' for k, v in args.items()])
        return Layer(
            {
                "summary": "s3proxy layer",
                "description": "s3proxy layer",
                "services": {
                    "s3proxy": {
                        "override": "replace",
                        "summary": "s3proxy daemon",
                        "command": f"java {arg_str} -jar /usr/bin/s3proxy --properties /dev/null",
                        "startup": "enabled",
                    }
                },
            }
        )

    def _set_s3proxy_version(self) -> bool:
        version = self._workload_version

        if version is None:
            logger.debug(
                "Cannot set workload version at this time: could not get s3proxy version."
            )
            return False

        self.unit.set_workload_version(version)
        return True

    @property
    def _workload_version(self) -> Optional[str]:
        if not self._container.can_connect():
            return None

        result, _ = self._container.exec(["/usr/bin/s3proxy", "--version"]).wait_output()
        result = result.strip()
        # The result looks like:
        # [s3proxy] E 01-16 18:23:47.925 main org.gaul.s3proxy.Main:279 |::] 2.0.0
        ver = re.sub(r".*?((\d+\.?)+)$", r"\1", result)
        if ver != result:
            return ver
        return result

    @property
    def hostname(self) -> str:
        """Unit's hostname."""
        return socket.getfqdn()

    @property
    def is_ready(self) -> bool:
        """Check whether the endpoint is really reachable."""
        client = boto3.client(
            service_name="s3",
            endpoint_url="http://127.0.0.1:8080",
            aws_access_key_id=self._credentials["identity"],
            aws_secret_access_key=self._credentials["credential"],
        )
        try:
            client.list_buckets()
            return True
        except exceptions.BotoCoreError:
            return False


if __name__ == "__main__":  # pragma: nocover
    main(S3ProxyK8SOperatorCharm)
