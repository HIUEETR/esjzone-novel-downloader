import sys
from pathlib import Path
from loguru import logger
from ruamel.yaml import YAML

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
        "account": {
            "username": "",
            "password": ""
        },
        "download": {
            "dir": "downloads",
            "download_format": "epub",
            "naming_mode": "book_name",
            "use_book_dir": False
        },
        "log": {
            "level": "INFO",
            "dir": "logs",
            "retention": 3
        }
    }

    def load(self):
        """
        加载配置文件，支持热加载
        """
        try:
            if not self._config_path.exists():
                logger.warning(f"配置文件不存在: {self._config_path.absolute()}，正在创建默认配置...")
                self._config_data = self._default_config
                self.save()
                logger.info("默认配置文件创建成功")
                return
            
            with open(self._config_path, 'r', encoding='utf-8') as f:
                data = self._yaml.load(f)
                if not data:
                    raise ValueError("配置文件为空")
                self._config_data = data
                
            logger.info("配置文件加载成功")
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def reload(self):
        """重新加载配置"""
        self.load()

    @property
    def account(self):
        return self._config_data.get('account', {})

    @property
    def cookie(self):
        return self._config_data.get('cookie', {})

    @property
    def log(self):
        return self._config_data.get('log', {})
    
    def get(self, key, default=None):
        """
        获取配置项，支持点号分隔，例如: log.level
        """
        keys = key.split('.')
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
        """
        keys = key.split('.')
        target = self._config_data
        for k in keys[:-1]:
            target = target.setdefault(k, {})
        target[keys[-1]] = value
    
    def save(self):
        """保存当前配置到文件"""
        try:
            # 确保 account 顺序: username, password
            if 'account' in self._config_data:
                account = self._config_data['account']
                if 'username' in account and 'password' in account:
                    # 如果 key 顺序不对，重新构建 account
                    keys = list(account.keys())
                    if keys.index('username') > keys.index('password'):
                        # 记录所有 key-value，并按正确顺序重新插入
                        temp_data = {}
                        for k in keys:
                            temp_data[k] = account.pop(k)
                        
                        # 构建新的 key 顺序
                        new_keys = []
                        for k in keys:
                            if k == 'password':
                                continue
                            if k == 'username':
                                new_keys.append('username')
                                new_keys.append('password')
                            else:
                                new_keys.append(k)
                        
                        # 重新插入
                        for k in new_keys:
                            if k in temp_data:
                                account[k] = temp_data[k]

            with open(self._config_path, 'w', encoding='utf-8') as f:
                self._yaml.dump(self._config_data, f)
            logger.info("配置文件保存成功")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            raise

# 全局配置实例
config = ConfigLoader()
