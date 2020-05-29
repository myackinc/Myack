import hmac
import hashlib
import base64
import binascii
import random
from abc import ABC, abstractmethod
from typing import TypeVar, ClassVar, Type, Callable, Optional, Any, Dict, Union

import validx
from aioconductor import Component
from cached_property import cached_property

from .exc import BaseError
from .timer import Timer
from .serializer import Serializer


TypeTokenEncoder = TypeVar("TypeTokenEncoder", bound=Type["TokenEncoder"])


class JWT(Component):
    algorithms: ClassVar[Dict[str, Type["TokenEncoder"]]] = {}

    serializer: Serializer
    timer: Timer

    encoders: Dict[str, "TokenEncoder"]

    async def on_setup(self) -> None:
        self.encoders = {}
        for sub, config in self.config["jwt"].rare_items():
            config = dict(config)
            alg = config.pop("alg")
            self.encoders[sub] = self.algorithms[alg](
                self.serializer, self.timer, sub=sub, **config
            )

    async def on_shutdown(self) -> None:
        del self.encoders

    @classmethod
    def add_algorithm(cls, algorithm: TypeTokenEncoder) -> TypeTokenEncoder:
        cls.algorithms[algorithm.alg] = algorithm
        return algorithm

    def encode(
        self, sub: str, payload: Dict[str, Any], header: Dict[str, Any] = None
    ) -> bytes:
        return self.encoders[sub].encode(payload, header)

    def decode(self, sub: str, token: Union[bytes, str]) -> Dict[str, Any]:
        return self.encoders[sub].decode(token)


class TokenEncoder(ABC):
    alg: ClassVar[str]

    serializer: Serializer
    timer: Timer

    sub: str
    ttl: int
    max_ttl: int

    def __init__(
        self,
        serializer: Serializer,
        timer: Timer,
        *,
        sub: str,
        ttl: int = 0,
        max_ttl: int = 0,
        **kw,
    ) -> None:
        self.serializer = serializer
        self.timer = timer
        self.sub = sub
        self.ttl = ttl
        self.max_ttl = max(max_ttl, ttl)

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.sub})>"

    def encode(self, payload: Dict[str, Any], header: Dict[str, Any] = None) -> bytes:
        header = dict(header or {}, typ="JWT", alg=self.alg)
        payload["sub"] = self.sub
        payload["iat"] = self.timer.tsnow()
        if self.ttl:
            payload["exp"] = payload["iat"] + self.ttl
        segments = [
            b64encode(self.serializer.dumpb(header)),
            b64encode(self.serializer.dumpb(payload)),
        ]
        signing_input = b".".join(segments)
        segments.append(b64encode(self.sign(payload, header, signing_input)))
        return b".".join(segments)

    def decode(self, token: Union[bytes, str]) -> Dict[str, Any]:
        try:
            if isinstance(token, str):
                token = token.encode("ascii")

            signing_input, signature_raw = token.rsplit(b".", 1)
            header_raw, payload_raw = signing_input.split(b".")

            header = self.serializer.loadb(b64decode(header_raw))
            payload = self.serializer.loadb(b64decode(payload_raw))
            signature = b64decode(signature_raw)
        except (ValueError, TypeError, binascii.Error):
            raise JWTInvalid(sub=self.sub)

        try:
            header = self.header_schema(header)
            payload = self.payload_schema(payload)
        except validx.exc.ValidationError:
            raise JWTInvalid(sub=self.sub)

        effective_signature = self.sign(payload, header, signing_input)
        if not hmac.compare_digest(signature, effective_signature):
            raise JWTInvalid(sub=self.sub)

        self.verify_claims(payload, header)
        return payload

    @cached_property
    def header_schema(self):
        return validx.Dict(
            {"typ": validx.Const("JWT"), "alg": validx.Const(self.alg)},
            extra=(validx.Str(), validx.Any()),
        )

    @cached_property
    def payload_schema(self):
        return validx.Dict(
            {
                "sub": validx.Const(self.sub),
                "iat": validx.Float(min=0),
                "exp": validx.Float(min=0),
            },
            optional=None if self.ttl else ("exp",),
            extra=(validx.Str(), validx.Any()),
        )

    def verify_claims(self, payload: Dict[str, Any], header: Dict[str, Any]) -> None:
        if self.ttl:
            if payload["exp"] + 60 < self.timer.tsnow():
                # Add 60 seconds leeway
                raise JWTExpired(sub=self.sub)
            if payload["exp"] - payload["iat"] > self.max_ttl:
                raise JWTInvalid(sub=self.sub)

    @abstractmethod
    def sign(
        self, payload: Dict[str, Any], header: Dict[str, Any], signing_input: bytes
    ) -> bytes:
        """Generate JWT signature"""


class HSEncoder(TokenEncoder):

    keylen: ClassVar[int]
    algorithm: ClassVar[Callable]

    key: bytes
    rot_salt: int
    rot_period: int

    _random: Optional[random.Random]

    def __init__(
        self,
        serializer: Serializer,
        timer: Timer,
        *,
        sub: str,
        key: str,
        ttl: int = 0,
        max_ttl: int = 0,
        rot_salt: int = 0,
        rot_period: int = 0,
    ) -> None:
        super().__init__(serializer, timer, sub=sub, ttl=ttl, max_ttl=max_ttl)
        self.key = binascii.unhexlify(key)
        self.ttl = ttl
        self.rot_salt = rot_salt
        self.rot_period = rot_period
        self._random = None if self.rot_period <= 0 else random.Random()
        assert (
            len(self.key) >= self.keylen
        ), f"Key of {self} should be at least {self.keylen} bytes"

    def get_effective_key(self, ts: float) -> bytes:
        if self._random is None:
            return self.key
        self._random.seed(self.rot_salt + int(ts) // self.rot_period, version=2)
        result = bytearray(len(self.key))
        for i, b in enumerate(self.key):
            result[i] = b ^ self._random.getrandbits(8)
        return result

    def sign(
        self, payload: Dict[str, Any], header: Dict[str, Any], signing_input: bytes
    ) -> bytes:
        effective_key = self.get_effective_key(payload["iat"])
        return hmac.new(effective_key, signing_input, self.algorithm).digest()


@JWT.add_algorithm
class HS256(HSEncoder):
    alg: ClassVar[str] = "HS256"
    keylen: ClassVar[int] = 32
    algorithm: ClassVar[Callable] = hashlib.sha256


@JWT.add_algorithm
class HS384(HSEncoder):
    alg: ClassVar[str] = "HS384"
    keylen: ClassVar[int] = 48
    algorithm: ClassVar[Callable] = hashlib.sha384


@JWT.add_algorithm
class HS512(HSEncoder):
    alg: ClassVar[str] = "HS512"
    keylen: ClassVar[int] = 64
    algorithm: ClassVar[Callable] = hashlib.sha512


class JWTError(BaseError, code="jwt"):
    """Base class of JWT errors"""


class JWTInvalid(JWTError, code="invalid"):
    message: str = "Invalid JWT"


class JWTExpired(JWTError, code="expired"):
    message: str = "Expired JWT"


def b64encode(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def b64decode(data: bytes) -> bytes:
    data += b"=" * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data)
