import jwt
from jwt import InvalidTokenError, DecodeError, ExpiredSignatureError
import os

class JWTDecoder:
    def __init__(self, public_key: str = os.getenv("JWT_PUBLIC_KEY")):
        self.public_key = public_key

    def call(self, token: str) -> dict:
        try:
            # Decode and verify the JWT
            decoded_payload = jwt.decode(
                token,
                self.public_key,
                algorithms=["RS256"]
            )
            return decoded_payload
        except ExpiredSignatureError:
            raise ValueError("The token has expired.")
        except DecodeError:
            raise ValueError("The token could not be decoded.")
        except InvalidTokenError:
            raise ValueError("The token is invalid.")
