import typing as t
from threading import Lock


class DictConfig:
    """
    Class providing a singleton configuration dictionary.

    Initialising the config with custom parameters is optional,
    but if you happen to re-use the same parameters over and over again
    in the `retry` function, this might save you some typing.

    Usage Example:
    ```python
    from tenacity import dict_config
    dict_config.set_config(
        wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6)
    )
    ```

    When calling retry, you can override the default config parameters or add some
    new ones:
    ```python
    @retry(wait=wait_random_exponential(min=10, max=30), stop=stop_after_attempt(10), reraise=True)
    ```

    Methods:
    - set_config: Sets multiple configuration parameters.
    - set_attribute: Sets a specific configuration attribute.
    - delete_attribute: Deletes a specific configuration attribute.
    - get_config: Retrieves the configuration dictionary.
    - __getattr__: Retrieves the value of a configuration attribute.
    - __getitem__: Retrieves the value of a configuration attribute using item access.
    - __contains__: Checks if a configuration attribute exists.
    - __repr__: Returns a string representation of the configuration object.
    """
    _instance = None
    _lock = Lock()      # For thread safety

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_config'):
            self._config = {}

    def set_config(self, **kwargs: t.Any) -> None:
        """Sets multiple configuration parameters."""
        self._config.update(kwargs)

    def set_attribute(self, name: str, value: t.Any) -> None:
        """Sets a specific configuration attribute."""
        self._config[name] = value

    def delete_attribute(self, name: str) -> None:
        """Deletes a specific configuration attribute."""
        if name in self._config:
            del self._config[name]
        else:
            raise KeyError(f'Attribute {name} not found in configuration.')

    def get_config(self, override: t.Optional[t.Dict[str, t.Any]] = None) -> t.Dict[str, t.Any]:
        """
        Retrieves the configuration dictionary.

        Parameters:
            override: Optional dictionary to override current configuration.

        Returns:
            A copy of the configuration dictionary, possibly modified with the overrides.
        """
        config = self._config.copy()
        if override:
            config.update(override)
        return config

    def reset_config(self):
        self._config = {}

    def __getattr__(self, name: str) -> t.Any:
        return self._config.get(name)

    def __getitem__(self, name: str) -> t.Any:
        return self._config[name]

    def __contains__(self, name: str) -> bool:
        return name in self._config

    def __repr__(self) -> str:
        return f'<DictConfig {self._config}>'


dict_config = DictConfig()
