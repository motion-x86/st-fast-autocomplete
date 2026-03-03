"""
vendor/jaraco/classes/properties.py
Minimal stub of jaraco.classes.properties required by keyring at import time.
Only NonDataProperty is used internally by keyring's backend priority system.
"""


class NonDataProperty:
    """
    A non-data descriptor equivalent to a read-only cached property.
    Mirrors the interface of jaraco.classes.properties.NonDataProperty.
    """

    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        value = self.func(obj)
        # Cache on the instance so subsequent accesses skip the descriptor
        obj.__dict__[self.name] = value
        return value
