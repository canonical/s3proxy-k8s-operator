#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import logging

import pytest
from helpers import oci_image, s3proxy_credentials, unit_address
from workload import S3Proxy

logger = logging.getLogger(__name__)

app_name = "s3proxy"
tester_app_name = "s3proxy-tester"
app_names = [app_name, tester_app_name]

s3proxy_resources = {
    "s3proxy-image": oci_image("./metadata.yaml", "s3proxy-image"),
}
s3proxy_tester_resources = {
    "s3proxy-tester-image": oci_image(
        "./tests/integration/s3proxy-tester/metadata.yaml", "s3proxy-tester-image"
    ),
}


@pytest.mark.abort_on_fail
async def test_object_storage_works(ops_test, s3proxy_charm, s3proxy_tester_charm):
    """Set resource limits and make sure they are applied."""
    await asyncio.gather(
        ops_test.model.deploy(
            s3proxy_charm,
            resources=s3proxy_resources,
            application_name=app_name,
            trust=True,
        ),
        ops_test.model.deploy(
            s3proxy_tester_charm,
            resources=s3proxy_tester_resources,
            application_name=tester_app_name,
            trust=True,
        ),
    )
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    await ops_test.model.add_relation(app_name, tester_app_name)
    await ops_test.model.wait_for_idle(apps=app_names, status="active")

    credentials = await s3proxy_credentials(ops_test, app_name)
    address = await unit_address(ops_test, app_name, 0)
    client = S3Proxy(
        host=address, secret_key=credentials["identity"], access_key=credentials["credential"]
    )
    assert any([tester_app_name == bucket["Name"] for bucket in client.list_buckets()])
    assert len(client.list_objects(bucket=tester_app_name)["Contents"]) > 0
