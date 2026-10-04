"""Password hashing, login sessions and client-address helpers.

Passwords are never stored: the server keeps a salted scrypt hash in its
environment and issues short-lived opaque sessions whose SHA-256 is the only
value written to SQLite. Uses the standard library only.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import ipaddress
import secrets

MIN_PASSWORD_LENGTH = 12
_SCRYPT_N_LOG2, _SCRYPT_R, _SCRYPT_P = 15, 8, 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    """Return ``scrypt$<log2 n>$<r>$<p>$<salt>$<hash>`` for ``password``."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"la contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**_SCRYPT_N_LOG2,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
        dklen=32,
    )
    return f"scrypt${_SCRYPT_N_LOG2}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def parse_password_hash(encoded: str) -> tuple[int, int, int, bytes, bytes]:
    """Validate the stored format; raises ``ValueError`` for anything else."""
    parts = encoded.split("$") if isinstance(encoded, str) else []
    if len(parts) != 6 or parts[0] != "scrypt":
        raise ValueError("password_hash debe tener formato scrypt$n$r$p$salt$hash")
    n_log2, r, p = (int(value) for value in parts[1:4])
    salt, digest = _unb64(parts[4]), _unb64(parts[5])
    if not (14 <= n_log2 <= 20 and 1 <= r <= 32 and 1 <= p <= 4 and len(salt) >= 16 and len(digest) == 32):
        raise ValueError("parámetros scrypt fuera de rango")
    return n_log2, r, p, salt, digest


def verify_password(password: str, encoded: str) -> bool:
    try:
        n_log2, r, p, salt, expected = parse_password_hash(encoded)
    except (ValueError, TypeError):
        return False
    candidate = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**n_log2, r=r, p=p, maxmem=_SCRYPT_MAXMEM, dklen=32
    )
    return hmac.compare_digest(candidate, expected)


def hash_fingerprint(encoded: str) -> str:
    """Short identifier of a configured hash; rotating the hash invalidates sessions."""
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_password() -> str:
    return secrets.token_urlsafe(18)


# Ranges a trusted-proxy network may fall in: loopback, private, and the
# shared address space (RFC 6598) that PaaS edges such as Railway's use. A
# network spanning public addresses would let anyone choose their own key.
_PROXY_NETWORK_RANGES = tuple(
    ipaddress.ip_network(value)
    for value in (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "100.64.0.0/10",
        "::1/128",
        "fc00::/7",
    )
)


def parse_trusted_proxy(value: str) -> str:
    """Normalize one proxy address or CIDR network; raises ``ValueError``.

    A single address may be any IP. A network must lie inside a loopback,
    private or shared-address range.
    """
    network = ipaddress.ip_network(value.strip(), strict=True)
    if network.num_addresses > 1 and not any(
        network.version == allowed.version and network.subnet_of(allowed) for allowed in _PROXY_NETWORK_RANGES
    ):
        raise ValueError("trusted proxy networks must be loopback, private or shared-address ranges")
    return str(network.network_address) if network.num_addresses == 1 else str(network)


_Networks = tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]


@functools.lru_cache(maxsize=8)
def _proxy_networks(trusted_proxies: tuple[str, ...]) -> _Networks:
    return tuple(ipaddress.ip_network(value) for value in trusted_proxies)


def _is_trusted(address: str, networks: _Networks) -> bool:
    try:
        ip = ipaddress.ip_address(address.strip())
    except ValueError:
        return False
    return any(ip in network for network in networks)


def client_address(peer: str, forwarded_for: str | None, trusted_proxies: tuple[str, ...]) -> str:
    """Use ``X-Forwarded-For`` only when the direct peer is a configured proxy.

    ``trusted_proxies`` holds addresses or networks. Walking the header from
    the right, trusted hops are skipped and the first other address is the
    client; entries to its left were supplied by that client and are ignored.
    """
    networks = _proxy_networks(trusted_proxies)
    if not forwarded_for or not _is_trusted(peer, networks):
        return peer
    for raw in reversed(forwarded_for.split(",")):
        try:
            candidate = str(ipaddress.ip_address(raw.strip()))
        except ValueError:
            return peer
        if not _is_trusted(candidate, networks):
            return candidate
    return peer


__all__ = [
    "MIN_PASSWORD_LENGTH",
    "client_address",
    "generate_password",
    "hash_fingerprint",
    "hash_password",
    "new_session_token",
    "parse_password_hash",
    "parse_trusted_proxy",
    "token_digest",
    "verify_password",
]
