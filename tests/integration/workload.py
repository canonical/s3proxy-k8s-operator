#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
from typing import Any, Dict, List, Optional

from boto3 import client as s3client


class S3Proxy:
    """A class which abstracts s3proxy access."""

    def __init__(
        self,
        *,
        host: Optional[str] = "localhost",
        port: Optional[int] = 8080,
        secret_key: Optional[str] = "secret",
        access_key: Optional[str] = "access",
    ):
        """Utility to access S3Proxy through boto3.

        Args:
            host: Optional host address of Grafana application, defaults to `localhost`
            port: Optional port on which Grafana service is exposed, defaults to `3000`
            secret_key: object storage secret key
            access_key: object storage access key
        """
        self.client = s3client(
            service_name="s3",
            endpoint_url=f"http://{host}:{port}",
            aws_access_key_id=secret_key,
            aws_secret_access_key=access_key,
        )

    def list_buckets(self) -> List[Dict[str, Any]]:
        """Return a list of buckets."""
        return self.client.list_buckets().get("Buckets", {})

    def list_objects(self, bucket: str) -> dict:
        return self.client.list_objects(Bucket=bucket)
