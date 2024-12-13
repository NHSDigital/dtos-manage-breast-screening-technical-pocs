import jwt
import os
from datetime import datetime, timedelta


class JWTEncoder:
    def __init__(self, private_key: str = os.getenv("JWT_PRIVATE_KEY")):
        self.private_key = private_key

    def call(self, user_id: int, first_name: str, last_name: str,
                       expiration_minutes: int = 60) -> str:
        payload = {
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "exp": datetime.utcnow() + timedelta(minutes=expiration_minutes)
        }
        token = jwt.encode(payload, self.private_key, algorithm="RS256")
        return token
