from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.configure_ops_monitoring import desired_policies


def main() -> None:
    policies = desired_policies(
        service_name="vpo-corp-api",
        job_name="vpo-royalty-report-job",
        check_id="uptime-test",
        channel_name="projects/test/notificationChannels/email-test",
    )
    assert len(policies) == 5
    assert len({policy["displayName"] for policy in policies}) == 5
    assert all(policy["enabled"] for policy in policies)
    assert all(policy["notificationChannels"] for policy in policies)

    filters = "\n".join(
        policy["conditions"][0]["conditionThreshold"]["filter"]
        for policy in policies
    )
    assert 'resource.label.service_name = "vpo-corp-api"' in filters
    assert 'resource.label.job_name = "vpo-royalty-report-job"' in filters
    assert 'metric.label.check_id = "uptime-test"' in filters
    assert 'metric.label.response_code_class = "5xx"' in filters
    assert 'metric.label.result = "failed"' in filters

    thresholds = {
        policy["displayName"]: policy["conditions"][0]["conditionThreshold"]["thresholdValue"]
        for policy in policies
    }
    assert thresholds["VPO API - latencia p95"] == 30000
    assert thresholds["VPO API - memoria"] == 0.85

    print("OPS monitoring contract OK")


if __name__ == "__main__":
    main()
