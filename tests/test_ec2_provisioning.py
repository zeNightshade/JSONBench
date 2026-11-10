import json
import subprocess
import sys
from pathlib import Path

import pytest

from infra import deploy_ec2


def test_launch_records_resources_and_uses_single_instance(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["deploy_ec2", "--ssh-cidr", "192.0.2.1/32", "--state", str(state_path), "--launch"],
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
    calls = []

    def aws(command, **kwargs):
        calls.append(command)
        operation = command[2]
        responses = {
            "get-caller-identity": {"Account": "test"},
            "describe-images": {
                "Images": [
                    {
                        "ImageId": "ami-test",
                        "CreationDate": "2026",
                        "Name": "RHEL-9.6",
                        "RootDeviceName": "/dev/sda1",
                    }
                ]
            },
            "describe-subnets": {
                "Subnets": [
                    {
                        "SubnetId": "subnet-test",
                        "AvailabilityZone": "a",
                        "AvailableIpAddressCount": 5,
                        "VpcId": "vpc-test",
                    }
                ]
            },
            "describe-instance-type-offerings": {"InstanceTypeOfferings": [{"Location": "a"}]},
            "import-key-pair": {},
            "create-security-group": {"GroupId": "sg-test"},
            "authorize-security-group-ingress": {},
            "wait": {},
            "run-instances": {"Instances": [{"InstanceId": "i-test"}]},
            "describe-instances": {
                "Reservations": [
                    {"Instances": [{"PublicIpAddress": "192.0.2.2", "BlockDeviceMappings": []}]}
                ]
            },
        }
        return json.dumps(responses[operation])

    monkeypatch.setattr(subprocess, "check_output", aws)
    deploy_ec2.main()
    state = json.loads(state_path.read_text())
    assert state["instance_id"] == "i-test"
    launch = next(c for c in calls if c[2] == "run-instances")
    assert launch[launch.index("--count") + 1] == "1"
    volumes = json.loads(launch[launch.index("--block-device-mappings") + 1])
    assert [v["Ebs"]["VolumeSize"] for v in volumes] == [128, 250]
    assert volumes[1]["Ebs"]["DeleteOnTermination"] is False
    assert all(v["Ebs"]["Encrypted"] for v in volumes)
    with pytest.raises(ValueError, match="State already exists"):
        deploy_ec2.main()
