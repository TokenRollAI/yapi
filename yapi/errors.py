class YapiError(Exception):
    pass


class YapiDeclarationError(YapiError):
    pass


class StateStoreError(YapiError):
    pass


class RuntimeExecutionError(YapiError):
    pass
