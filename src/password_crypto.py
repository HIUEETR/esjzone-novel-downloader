"""本机绑定的 account.password 加解密（Fernet + machine-id）。

磁盘形态: enc:v1:<fernet-token>
内存/登录: 明文密码
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

import machineid
from cryptography.fernet import Fernet, InvalidToken

PASSWORD_PREFIX = "enc:v1:"
_KEY_NAMESPACE = "esjzone-novel-downloader/account.password/v1"


class PasswordCryptoError(Exception):
    """密码加解密失败（常见于跨机器或配置损坏）。"""


def is_encrypted_password(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(PASSWORD_PREFIX)


def _normalize_machine_id(machine_id: str | None = None) -> str:
    if machine_id:
        return str(machine_id).strip()
    # machineid.id() 在部分环境可能抛错；交给调用方处理
    return str(machineid.id()).strip()


def derive_fernet_key(machine_id: str | None = None) -> bytes:
    """由 machine-id 派生 Fernet key（url-safe base64 of 32 raw bytes）。"""
    mid = _normalize_machine_id(machine_id)
    digest = hashlib.sha256(f"{_KEY_NAMESPACE}:{mid}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=4)
def _fernet_for(machine_id: str) -> Fernet:
    return Fernet(derive_fernet_key(machine_id))


def get_fernet(machine_id: str | None = None) -> Fernet:
    mid = _normalize_machine_id(machine_id)
    return _fernet_for(mid)


def encrypt_password(plaintext: str, machine_id: str | None = None) -> str:
    """明文 -> enc:v1:...；空串保持空串。"""
    if plaintext is None:
        return ""
    text = str(plaintext)
    if text == "":
        return ""
    if is_encrypted_password(text):
        return text
    token = get_fernet(machine_id).encrypt(text.encode("utf-8")).decode("ascii")
    return f"{PASSWORD_PREFIX}{token}"


def decrypt_password(stored: str, machine_id: str | None = None) -> str:
    """enc:v1:... -> 明文；非加密字符串原样返回（兼容旧配置）。"""
    if stored is None:
        return ""
    text = str(stored)
    if text == "":
        return ""
    if not is_encrypted_password(text):
        return text
    token = text[len(PASSWORD_PREFIX) :].encode("ascii")
    try:
        return get_fernet(machine_id).decrypt(token).decode("utf-8")
    except InvalidToken as e:
        raise PasswordCryptoError(
            "无法解密 account.password（可能是跨机器使用或配置已损坏）"
        ) from e
    except Exception as e:
        raise PasswordCryptoError(f"解密 account.password 失败: {e}") from e


def seal_password(value: str, machine_id: str | None = None) -> str:
    """写入磁盘前密封：已是密文则保持，明文则加密。"""
    return encrypt_password(value, machine_id=machine_id)


def reveal_password(value: str, machine_id: str | None = None) -> str:
    """读出供登录使用：密文解密，明文透传。"""
    return decrypt_password(value, machine_id=machine_id)
