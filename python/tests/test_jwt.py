import hmac
import binascii

import pytest
from configtree import Tree

from myack.jwt import JWT, JWTInvalid, JWTExpired, b64encode, b64decode


@pytest.fixture(
    params=[
        {
            "alg": "HS256",
            "key": "c74c46a37f7523e8c8d7a5fbf03125daf7075a3d93a5a02a5b4f92b01916cb72",
        },
        {
            "alg": "HS384",
            "key": (
                "23a4448121b6db152bc844a4302e4230"
                "aabdfdac0f81e7a3984f4e97bbe39b0f"
                "658f577c54059f2cfec848f20cc6c4f1"
            ),
        },
        {
            "alg": "HS512",
            "key": (
                "93f8a1d030d26bdd5044dc294534b8f6"
                "5285bf267e8daee7b5e3383d2cabda19"
                "636816b6afe046a47aeb94712bc372b4"
                "805de92fbe6f168face8773e6e23cd13"
            ),
        },
    ]
)
def config(request):
    result = Tree()
    result.branch("jwt.test").update(request.param)
    return result


@pytest.mark.asyncio
async def test_jwt(conductor, config):
    jwt = await conductor(JWT, config=config)
    assert "test" in jwt.encoders
    assert repr(jwt.encoders["test"]) == f"<{config['jwt.test.alg']}(test)>"

    now = jwt.timer.tsnow()
    token = jwt.encode("test", {"foo": "bar"})
    payload = jwt.decode("test", token)
    assert payload["foo"] == "bar"

    payload = jwt.decode("test", token.decode("utf-8"))
    assert payload["foo"] == "bar"

    signing_input, signature = token.rsplit(b".", 1)
    header, payload = signing_input.split(b".")

    header = jwt.serializer.loads(b64decode(header))
    payload = jwt.serializer.loads(b64decode(payload))
    signature = b64decode(signature)
    effective_signature = hmac.new(
        binascii.unhexlify(config["jwt.test.key"]),
        signing_input,
        jwt.encoders["test"].algorithm,
    ).digest()

    assert header == {"typ": "JWT", "alg": config["jwt.test.alg"]}
    assert payload["foo"] == "bar"
    assert now <= payload["iat"] < now + 0.001
    assert signature == effective_signature

    invalid_signature = hmac.new(
        binascii.unhexlify(config["jwt.test.key"]) + b"xxx",
        signing_input,
        jwt.encoders["test"].algorithm,
    ).digest()
    invalid_token = b".".join((signing_input, b64encode(invalid_signature)))

    with pytest.raises(JWTInvalid) as info:
        jwt.decode("test", invalid_token)
    assert info.value.message == "Invalid JWT"
    assert info.value.data == {"sub": "test"}


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [0, 60])
async def test_jwt_ttl(conductor, config, ttl):
    config["jwt.test"].update(ttl=ttl)

    jwt = await conductor(JWT, config=config)

    token = jwt.encode("test", {"foo": "bar"})
    payload = jwt.decode("test", token)
    assert payload["foo"] == "bar"
    if ttl:
        assert payload["exp"] == payload["iat"] + ttl

    jwt.timer.shift(seconds=70)  # Within leeway
    payload = jwt.decode("test", token)
    assert payload["foo"] == "bar"

    jwt.timer.shift(seconds=55)  # Outside leeway
    if ttl:
        with pytest.raises(JWTExpired) as info:
            jwt.decode("test", token)
        assert info.value.message == "Expired JWT"
        assert info.value.data == {"sub": "test"}
    else:
        payload = jwt.decode("test", token)
        assert payload["foo"] == "bar"

    token_2 = jwt.encode("test", {"foo": "bar"})
    payload_2 = jwt.decode("test", token_2)
    assert payload_2["foo"] == "bar"


@pytest.mark.asyncio
@pytest.mark.parametrize("max_ttl", [0, 90])
async def test_jwt_max_ttl(conductor, config, max_ttl):
    config["jwt.test"].update(ttl=60, max_ttl=max_ttl)

    jwt = await conductor(JWT, config=config)

    token = jwt.encode("test", {"foo": "bar"})
    payload = jwt.decode("test", token)
    assert payload["foo"] == "bar"

    header, payload, _ = token.split(b".")
    payload = jwt.serializer.loads(b64decode(payload))
    payload["exp"] += 20
    payload = b64encode(jwt.serializer.dumps(payload))
    signature = b64encode(
        hmac.new(
            binascii.unhexlify(config["jwt.test.key"]),
            b".".join((header, payload)),
            jwt.encoders["test"].algorithm,
        ).digest()
    )
    token = b".".join((header, payload, signature))

    if max_ttl:
        payload = jwt.decode("test", token)
        assert payload["foo"] == "bar"
    else:
        # max_ttl == ttl
        with pytest.raises(JWTInvalid) as info:
            jwt.decode("test", token)
        assert info.value.message == "Invalid JWT"
        assert info.value.data == {"sub": "test"}

    header, payload, _ = token.split(b".")
    payload = jwt.serializer.loads(b64decode(payload))
    payload["exp"] += 20
    payload = b64encode(jwt.serializer.dumps(payload))
    signature = b64encode(
        hmac.new(
            binascii.unhexlify(config["jwt.test.key"]),
            b".".join((header, payload)),
            jwt.encoders["test"].algorithm,
        ).digest()
    )
    token = b".".join((header, payload, signature))

    with pytest.raises(JWTInvalid) as info:
        jwt.decode("test", token)
    assert info.value.message == "Invalid JWT"
    assert info.value.data == {"sub": "test"}


@pytest.mark.asyncio
@pytest.mark.parametrize("rot_period", [0, 60])
@pytest.mark.parametrize("rot_salt", [0, 1])
async def test_jwt_rot(conductor, config, rot_period, rot_salt):
    config["jwt.test"].update(rot_period=rot_period, rot_salt=rot_salt)

    jwt = await conductor(JWT, config=config)

    token = jwt.encode("test", {"foo": "bar"})
    payload = jwt.decode("test", token)
    assert payload["foo"] == "bar"

    signing_input, signature = token.rsplit(b".", 1)
    signature = b64decode(signature)
    effective_signature = hmac.new(
        binascii.unhexlify(config["jwt.test.key"]),
        signing_input,
        jwt.encoders["test"].algorithm,
    ).digest()

    if rot_period:
        assert signature != effective_signature
    else:
        assert signature == effective_signature


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    [
        b"&invalid_base64",
        b64encode(b"Invalid JSON"),
        b64encode(b"null"),
        b64encode(b"{}"),
    ],
)
@pytest.mark.parametrize(
    "payload",
    [
        b"&invalid_base64",
        b64encode(b"Invalid JSON"),
        b64encode(b"null"),
        b64encode(b"{}"),
    ],
)
async def test_jwt_invalid(conductor, config, header, payload):
    jwt = await conductor(JWT, config=config)

    signature = b64encode(
        hmac.new(
            binascii.unhexlify(config["jwt.test.key"]),
            b".".join((header, payload)),
            jwt.encoders["test"].algorithm,
        ).digest()
    )
    token = b".".join((header, payload, signature))
    with pytest.raises(JWTInvalid) as info:
        jwt.decode("test", token)
    assert info.value.message == "Invalid JWT"
    assert info.value.data == {"sub": "test"}
