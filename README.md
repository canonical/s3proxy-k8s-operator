# s3proxy Charmed Operator for K8s

## Description

The s3proxy Charmed Operator provides an abstraction around S3-compatible object storage which is able to proxy requests to a variety of backends. Filesystem storage is the default, unless specified.

## Usage

The s3proxy Operator may be deployed using the Juju command line:

```sh
$ juju deploy s3proxy-k8s --trust
```

## OCI Images

This charm by default uses the last stable release of the [canonical/s3proxy](https://ghcr.io/canonical/s3proxy:2.0.0) image.
