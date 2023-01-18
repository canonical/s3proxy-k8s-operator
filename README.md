# s3proxy Charmed Operator for K8s

## Description

The s3proxy Charmed Operator provides an abstraction around S3-compatible object storage which is able to proxy
requests to a variety of backends. Filesystem storage is the default, unless specified.

## Usage

The s3proxy Operator may be deployed using the Juju command line:

```sh
$ juju deploy s3proxy-k8s --trust
```

The default authorization scheme is anonymous access, but `juju config s3proxy-k8s authorization=aws-v2-or-v4` may be
used to enforce authentication.

Similarly, the `identity` and `credentials` configuration keys may be used for `ACCESS_KEY` and `SECRET_KEY`.

To connect with `s3cmd`, ensure that your configuration file (`~/.s3cmd` by default) has the following values set after
configuring (`s3cmd --configure`)

    host_base = {unit_ip}:8080
    host_bucket = {unit_ip}:8080
    use_https = No
    signature_v2 = False

If no value is specified for `identity` or `credentials`, one will be automatically generated. To retrieve it if anonymous
access is disabled:

```sh
$ juju run s3cmd-k8s/0 get-credentials
```

## OCI Images

This charm by default uses the last stable release of the [canonical/s3proxy](https://ghcr.io/canonical/s3proxy:2.0.0) image.
