from unittest import TestCase
from unittest.mock import Mock

from minio.commonconfig import ENABLED, Filter
from minio.lifecycleconfig import Expiration, LifecycleConfig, Rule

from scripts.init_minio import ensure_lifecycle, expiration_rule


class MinioLifecycleTests(TestCase):
    def test_adds_rule_when_bucket_has_no_lifecycle(self):
        client = Mock()
        client.get_bucket_lifecycle.return_value = None
        expected = expiration_rule("owned", "batch-imports/", 7)

        ensure_lifecycle(client, "imports", [expected])

        config = client.set_bucket_lifecycle.call_args.args[1]
        self.assertEqual(config.rules, [expected])

    def test_repeat_run_does_not_write_duplicate_rule(self):
        client = Mock()
        current = expiration_rule("owned", "batch-imports/", 7)
        client.get_bucket_lifecycle.return_value = LifecycleConfig([current])

        ensure_lifecycle(
            client,
            "imports",
            [expiration_rule("owned", "batch-imports/", 7)],
        )

        client.set_bucket_lifecycle.assert_not_called()

    def test_updates_owned_rule_and_preserves_other_rules(self):
        client = Mock()
        unrelated = Rule(
            ENABLED,
            rule_filter=Filter(prefix="manual/"),
            rule_id="unrelated",
            expiration=Expiration(days=90),
        )
        client.get_bucket_lifecycle.return_value = LifecycleConfig(
            [unrelated, expiration_rule("owned", "batch-imports/", 14)]
        )

        ensure_lifecycle(
            client,
            "imports",
            [expiration_rule("owned", "batch-imports/", 7)],
        )

        rules = client.set_bucket_lifecycle.call_args.args[1].rules
        self.assertIs(rules[0], unrelated)
        self.assertEqual(rules[1].rule_id, "owned")
        self.assertEqual(rules[1].expiration.days, 7)
