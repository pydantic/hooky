"""
Blocks are a simple alternative for MagicMock which require all attributes to be defined in advance.

See usage in ./logic.py for an example of usage.
"""

from abc import ABC, abstractmethod
from copy import copy
from dataclasses import dataclass
from typing import Any


@dataclass
class History(ABC):
    path: list[str | int]

    def path_str(self):
        return '.'.join(str(i) for i in self.path)

    @abstractmethod
    def display(self):
        raise NotImplementedError


class Block(ABC):
    _name: str

    def __init__(self):
        self.__path__: list[str | int] = []
        self.__raw_history__: list[History] = []

    def _set_history(self, path: list[str | int], history: list[History]) -> None:
        self.__path__ = path
        self.__raw_history__ = history

    def _path_append(self, *attrs: str | int) -> list[str | int]:
        new_path = copy(self.__path__)
        if new_path and attrs and new_path[-1] == attrs[0]:
            new_path.pop()
        return new_path + list(attrs)

    @property
    def __history__(self):
        return [f'{h.path_str()}: {h.display()}' for h in self.__raw_history__]

    @property
    def __name__(self) -> str:
        return f'{self.__class__.__name__}({self._name})'

    @abstractmethod
    def __repr__(self):
        raise NotImplementedError


@dataclass
class HistoryGetAttr(History):
    attr: Any

    def display(self):
        return repr(self.attr)


Undefined = object()


class AttrBlock(Block):
    def __init__(self, __name: str, /, **attrs: Any):
        super().__init__()
        self._name = __name
        self._attrs = attrs

    def __getattr__(self, item) -> Any:
        if (attr := self._attrs.get(item, Undefined)) is not Undefined:
            path = self._path_append(item)
            if isinstance(attr, Block):
                attr._set_history(path, self.__raw_history__)
            # self.__raw_history__.append(HistoryGetAttr(path, attr))
            return attr
        else:
            raise AttributeError(f'{self.__name__!r} object has no attribute {item!r}')

    def __repr__(self):
        attrs_kwargs = ', '.join(f'{k}={v!r}' for k, v in self._attrs.items())
        return f'{self.__class__.__name__}({self._name!r}, {attrs_kwargs})'


@dataclass
class HistoryCall(History):
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    return_value: Any
    raises: Any = None

    def display(self):
        args = ', '.join([repr(i) for i in self.args] + [f'{k}={v!r}' for k, v in self.kwargs.items()])
        if self.raises:
            return f'raises {self.raises!r}'
        if self.return_value is not None:
            extra = f' -> {self.return_value!r}'
        else:
            extra = ''
        return f'Call({args}){extra}'


class CallableBlock(Block):
    def __init__(self, name: str, return_value: Any = None, *, raises: Exception = None):
        super().__init__()
        self._name = name
        self._return_value = return_value
        self._raises = raises

    def __call__(self, *args, **kwargs):
        path = self._path_append(self._name)
        if self._raises is not None:
            raises = self._raises
            if isinstance(raises, Block):
                raises._set_history(path, self.__raw_history__)
            self.__raw_history__.append(HistoryCall(path, args, kwargs, None, raises))
            raise raises
        else:
            return_value = self._return_value
            if isinstance(return_value, Block):
                return_value._set_history(path, self.__raw_history__)
            self.__raw_history__.append(HistoryCall(path, args, kwargs, return_value))
            return return_value

    def __repr__(self):
        if self._return_value is None:
            return f'{self.__class__.__name__}({self._name!r})'
        else:
            return f'{self.__class__.__name__}({self._name!r}, {self._return_value!r})'


@dataclass
class HistoryIter(History):
    items: tuple[Any, ...]

    def display(self):
        args = ', '.join(repr(i) for i in self.items)
        return f'Iter({args})'


class IterBlock(Block):
    def __init__(self, name: str, *items: Any):
        super().__init__()
        self._name = name
        self._items = items

    def __iter__(self, *args, **kwargs):
        path = self._path_append(self._name)
        items = self._items
        for i, item in enumerate(items):
            if isinstance(item, Block):
                item._set_history(self._path_append(self._name, i), self.__raw_history__)
        self.__raw_history__.append(HistoryIter(path, items))
        return iter(items)

    def __repr__(self):
        args = (self._name,) + self._items
        return f'{self.__class__.__name__}({", ".join(repr(a) for a in args)})'
