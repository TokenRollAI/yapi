class YapiError(Exception):
    pass


class YapiDeclarationError(YapiError):
    pass


class RuntimeExecutionError(YapiError):
    pass


class YapiUsageWarning(UserWarning):
    pass
