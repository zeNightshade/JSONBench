"""Provision one tagged Sydney pilot host using the AWS CLI; retain data on termination."""

import argparse
import json
import subprocess
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--region", default="ap-southeast-2", choices=["ap-southeast-2", "ap-southeast-4"]
    )
    parser.add_argument("--ssh-cidr", required=True, help="Trusted administrator IPv4 /32 only")
    parser.add_argument("--state", required=True)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    import ipaddress

    network = ipaddress.ip_network(args.ssh_cidr)
    if network.version != 4 or network.prefixlen != 32:
        raise ValueError("SSH access must be one IPv4 address (/32)")
    path = Path(args.state).resolve()
    if path.exists():
        raise ValueError(
            "State already exists; inspect/reuse the recorded instance, do not relaunch"
        )

    def aws(*parts):
        command = ["aws", *parts, "--region", args.region, "--output", "json", "--no-cli-pager"]
        result = subprocess.check_output(command, text=True)
        return json.loads(result) if result.strip() else {}

    account = aws("sts", "get-caller-identity")["Account"]
    images = aws(
        "ec2",
        "describe-images",
        "--owners",
        "309956199498",
        "--filters",
        "Name=name,Values=RHEL-9.6*",
        "Name=architecture,Values=x86_64",
        "Name=state,Values=available",
    )["Images"]
    image = max(images, key=lambda item: item["CreationDate"])
    subnets = aws("ec2", "describe-subnets", "--filters", "Name=default-for-az,Values=true")[
        "Subnets"
    ]
    offerings = aws(
        "ec2",
        "describe-instance-type-offerings",
        "--location-type",
        "availability-zone",
        "--filters",
        "Name=instance-type,Values=m6a.xlarge",
    )["InstanceTypeOfferings"]
    zones = {item["Location"] for item in offerings}
    subnet = next(
        s
        for s in sorted(subnets, key=lambda s: s["AvailabilityZone"])
        if s["AvailabilityZone"] in zones and s["AvailableIpAddressCount"] > 0
    )
    state = dict(
        account=account,
        region=args.region,
        image_id=image["ImageId"],
        image_name=image["Name"],
        subnet_id=subnet["SubnetId"],
        availability_zone=subnet["AvailabilityZone"],
        instance_type="m6a.xlarge",
        root_gib=128,
        data_gib=250,
        volume_type="gp3",
        iops=3000,
        throughput_mib_s=125,
    )
    print(json.dumps(state, indent=2))
    if not args.launch:
        return
    name = "jsonbench-paper-" + uuid4().hex[:8]
    state["name"] = name
    path.parent.mkdir(parents=True, exist_ok=True)

    def save():
        path.write_text(json.dumps(state, indent=2))
        path.chmod(0o600)

    save()
    key_path = Path.home() / ".ssh" / name
    key_path.parent.mkdir(mode=0o700, exist_ok=True)
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-f", str(key_path)], check=True)
    aws(
        "ec2",
        "import-key-pair",
        "--key-name",
        name,
        "--public-key-material",
        "fileb://" + str(key_path) + ".pub",
    )
    state["key_path"] = str(key_path)
    state["key_name"] = name
    save()
    group = aws(
        "ec2",
        "create-security-group",
        "--group-name",
        name,
        "--description",
        "JSONBench SSH from administrator only; no database ingress",
        "--vpc-id",
        subnet["VpcId"],
    )["GroupId"]
    state["security_group_id"] = group
    save()
    aws(
        "ec2",
        "authorize-security-group-ingress",
        "--group-id",
        group,
        "--protocol",
        "tcp",
        "--port",
        "22",
        "--cidr",
        args.ssh_cidr,
    )
    mappings = [
        dict(
            DeviceName=device,
            Ebs=dict(
                VolumeSize=size,
                VolumeType="gp3",
                Iops=3000,
                Throughput=125,
                Encrypted=True,
                DeleteOnTermination=delete,
            ),
        )
        for device, size, delete in [(image["RootDeviceName"], 128, True), ("/dev/sdf", 250, False)]
    ]
    tags = [{"Key": "Name", "Value": name}, {"Key": "Project", "Value": "JSONBench"}]
    response = aws(
        "ec2",
        "run-instances",
        "--image-id",
        image["ImageId"],
        "--instance-type",
        "m6a.xlarge",
        "--count",
        "1",
        "--key-name",
        name,
        "--client-token",
        name,
        "--network-interfaces",
        json.dumps(
            [
                dict(
                    DeviceIndex=0,
                    SubnetId=subnet["SubnetId"],
                    Groups=[group],
                    AssociatePublicIpAddress=True,
                )
            ]
        ),
        "--metadata-options",
        "HttpTokens=required,HttpEndpoint=enabled",
        "--block-device-mappings",
        json.dumps(mappings),
        "--tag-specifications",
        json.dumps([{"ResourceType": kind, "Tags": tags} for kind in ("instance", "volume")]),
        "--user-data",
        "file://" + str(Path(__file__).with_name("bootstrap.sh")),
    )
    state["instance_id"] = response["Instances"][0]["InstanceId"]
    save()
    aws("ec2", "wait", "instance-running", "--instance-ids", state["instance_id"])
    details = aws("ec2", "describe-instances", "--instance-ids", state["instance_id"])[
        "Reservations"
    ][0]["Instances"][0]
    state["public_ip"] = details.get("PublicIpAddress")
    state["volumes"] = details["BlockDeviceMappings"]
    save()
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
