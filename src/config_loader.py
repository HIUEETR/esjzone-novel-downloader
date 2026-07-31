from pathlib import Path

from loguru import logger
from ruamel.yaml import YAML

from .password_crypto import (
    PasswordCryptoError,
    is_encrypted_password,
    reveal_password,
    seal_password,
)


class ConfigLoader:
    _instance = None
    _config_data = {}
    _config_path = Path("config.yaml")
    _yaml = YAML()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            # 配置 ruamel.yaml
            cls._yaml.preserve_quotes = True
            cls._yaml.indent(mapping=2, sequence=4, offset=2)
            cls._instance.load()
        return cls._instance

    # 配置文件不存在时的默认值
    _default_config = {
        "account": {"username": "", "password": ""},
        "download": {
            "dir": "downloads",
            "download_format": "epub",
            "naming_mode": "book_name",
            "use_book_dir": False,
            "max_threads": 5,
            "timeout_seconds": 180,
            "retry_attempts": 3,
            "retry_delays": [10, 15, 30],
        },
        "log": {"level": "INFO", "dir": "logs", "retention": 3},
    }

    def load(self):
        """
        加载配置文件，支持热加载。
        若 account.password 仍为明文，则自动升级为 enc:v1: 并写回。
        """
        try:
            if not self._config_path.exists():
                logger.warning(
                    f"配置文件不存在: {self._config_path.absolute()}，正在创建默认配置..."
                )
                self._config_data = self._default_config
                self.save()
                logger.info("默认配置文件创建成功")
                return

            with open(self._config_path, "r", encoding="utf-8") as f:
                data = self._yaml.load(f)
                if not data:
                    raise ValueError("配置文件为空")
                self._config_data = data

            if self._upgrade_plaintext_password():
                self.save()
                logger.info("已将 account.password 从明文升级为 enc:v1: 密文")

            logger.info("配置文件加载成功")

        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def reload(self):
        """重新加载配置"""
        self.load()

    def _raw_account(self) -> dict:
        account = self._config_data.get("account")
        if not isinstance(account, dict):
            account = {}
            self._config_data["account"] = account
        return account

    def _upgrade_plaintext_password(self) -> bool:
        """明文密码自动密封；已是密文则校验可解密。返回是否需要 save。"""
        account = self._raw_account()
        raw = account.get("password", "")
        if raw is None:
            raw = ""
        raw = str(raw)
        if raw == "":
            return False

        if is_encrypted_password(raw):
            try:
                reveal_password(raw)
            except PasswordCryptoError as e:
                logger.error(str(e))
                # 不删除配置，保留密文让用户手工处理
            return False

        try:
            account["password"] = seal_password(raw)
            return True
        except Exception as e:
            logger.error(f"自动加密 account.password 失败: {e}")
            return False

    def get_password(self) -> str:
        """获取解密后的登录密码（供登录逻辑使用）。"""
        raw = self._raw_account().get("password", "") or ""
        try:
            return reveal_password(str(raw))
        except PasswordCryptoError as e:
            logger.error(str(e))
            return ""

    def set_password(self, password: str) -> None:
        """设置密码并以 enc:v1: 形式写入内存配置（需再 save）。"""
        self._raw_account()["password"] = seal_password(password or "")

    @property
    def account(self):
        """返回账号视图；password 字段为解密后的明文，便于现有调用方兼容。"""
        raw = dict(self._raw_account())
        stored = raw.get("password", "") or ""
        try:
            raw["password"] = reveal_password(str(stored))
        except PasswordCryptoError as e:
            logger.error(str(e))
            raw["password"] = ""
        return raw

    @property
    def cookie(self):
        return self._config_data.get("cookie", {})

    @property
    def log(self):
        return self._config_data.get("log", {})

    def get(self, key, default=None):
        """
        获取配置项，支持点号分隔，例如: log.level
        account.password 自动解密。
        """
        keys = key.split(".")
        if key == "account.password" or keys == ["account", "password"]:
            raw = self._raw_account().get("password", None)
            if raw is None or str(raw) == "":
                return "" if default is None else default
            try:
                return reveal_password(str(raw))
            except PasswordCryptoError as e:
                logger.error(str(e))
                return "" if default is None else default

        value = self._config_data
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key, value):
        """
        设置配置项，支持点号分隔，例如: log.level
        account.password 自动加密存储。
        """
        keys = key.split(".")
        if key == "account.password" or keys == ["account", "password"]:
            self.set_password("" if value is None else str(value))
            return

        target = self._config_data
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value

    def save(self):
        """保存当前配置到文件（保证 password 为密封形态）。"""
        try:
            # 落盘前再密封一次，防止内存中残留明文
            account = self._raw_account()
            if "password" in account:
                account["password"] = seal_password(str(account.get("password") or ""))

            # 确保 account 顺序: username, password
            if "account" in self._config_data:
                account = self._config_data["account"]
                if "username" in account and "password" in account:
                    # 如果 key 顺序不对，重新构建 account
                    keys = list(account.keys())
                    if keys.index("username") > keys.index("password"):
                        # 记录所有 key-value，并按正确顺序重新插入
                        temp_data = {}
                        for k in keys:
                            temp_data[k] = account.pop(k)

                        # 构建新的 key 顺序
                        new_keys = []
                        for k in keys:
                            if k == "password":
                                continue
                            if k == "username":
                                new_keys.append("username")
                                new_keys.append("password")
                            else:
                                new_keys.append(k)

                        # 重新插入
                        for k in new_keys:
                            if k in temp_data:
                                account[k] = temp_data[k]

            with open(self._config_path, "w", encoding="utf-8") as f:
                self._yaml.dump(self._config_data, f)
            logger.info("配置文件保存成功")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise


# 全局配置实例
config = ConfigLoader()
