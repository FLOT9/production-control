import hashlib
import hmac


class WebhookSigner:
    @staticmethod
    def sign(
        *,
        secret_key: str,
        timestamp: str,
        body: bytes,
    ) -> str:
        signed_data = timestamp.encode("ascii") + b"." + body

        digest = hmac.new(
            secret_key.encode("utf-8"),
            signed_data,
            hashlib.sha256,
        ).hexdigest()

        return f"v1={digest}"
