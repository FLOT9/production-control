import os

from minio import Minio
from minio.commonconfig import ENABLED, Filter
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule


def retention_days(name: str, default: int) -> int:
    days = int(os.getenv(name, str(default)))
    if days < 1:
        raise ValueError(f"{name} must be at least 1 day")
    return days


def expiration_rule(rule_id: str, prefix: str, days: int) -> Rule:
    return Rule(
        ENABLED,
        rule_filter=Filter(prefix=prefix),
        rule_id=rule_id,
        expiration=Expiration(days=days),
    )


def same_rule(current: Rule, expected: Rule) -> bool:
    return (
        current.status == expected.status
        and current.rule_filter is not None
        and current.rule_filter.prefix == expected.rule_filter.prefix
        and current.expiration is not None
        and current.expiration.days == expected.expiration.days
    )


def ensure_lifecycle(client: Minio, bucket: str, managed: list[Rule]) -> None:
    config = client.get_bucket_lifecycle(bucket)
    existing = config.rules if config is not None else []
    by_id = {rule.rule_id: rule for rule in existing}

    if all(
        rule.rule_id in by_id and same_rule(by_id[rule.rule_id], rule)
        for rule in managed
    ):
        print(f"Lifecycle rules already configured for {bucket}")
        return

    managed_ids = {rule.rule_id for rule in managed}
    other_rules = [rule for rule in existing if rule.rule_id not in managed_ids]
    client.set_bucket_lifecycle(bucket, LifecycleConfig(other_rules + managed))
    print(f"Lifecycle rules configured for {bucket}")


def main() -> None:
    rules = {
        "imports": [
            expiration_rule(
                "production-control-imports",
                "batch-imports/",
                retention_days("MINIO_IMPORT_RETENTION_DAYS", 7),
            ),
        ],
        "reports": [
            expiration_rule(
                "production-control-exports",
                "batch-exports/",
                retention_days("MINIO_EXPORT_RETENTION_DAYS", 7),
            ),
            expiration_rule(
                "production-control-reports",
                "production-summary/",
                retention_days("MINIO_REPORT_RETENTION_DAYS", 30),
            ),
        ],
        "exports": [],
    }

    client = Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ROOT_USER"],
        secret_key=os.environ["MINIO_ROOT_PASSWORD"],
        secure=False,
    )
    for bucket, managed in rules.items():
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            print(f"Bucket created: {bucket}")
        if managed:
            ensure_lifecycle(client, bucket, managed)


if __name__ == "__main__":
    main()
