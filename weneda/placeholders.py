import re
from functools import partial
from typing import Any, Callable, Coroutine


PlaceholderFuncType = Callable[[Any, str, int], Coroutine[Any, Any, str]]


class Placeholder:
    def __init__(
        self, 
        *, 
        name: str, 
        syntax: str | None, 
        regex: str | None
    ) -> None:
        self.formatter: Formatter | None = None
        self.name: str = name
        self.syntax: str | None = syntax
        self.pattern: re.Pattern | None = re.compile(regex) if regex else None
    
    async def process(self, name: str, depth: int) -> str:
        return None


def placeholder(
    *, 
    name: str | None = None,
    syntax: str | None = None, 
    regex: str | None = None
) -> Callable[[PlaceholderFuncType], Placeholder]:
    def helper(func: PlaceholderFuncType) -> Placeholder:
        func.__placeholder_args__ = {
            'name': name if name is not None else func.__name__,
            'syntax': syntax,
            'regex': regex
        }
        return func

    return helper


class Formatter:
    """
    Base class for placeholder formatters.
    """
    def __init_subclass__(cls) -> None:
        cls.__placeholder_items__ = [
            member
            for base in reversed(cls.__mro__)
            for member in base.__dict__.values()
            if hasattr(member, '__placeholder_args__')
        ]

    def __init__(
        self, 
        opener: str = '{', 
        closer: str = '}',
        *,
        escape: str | None = '\\'
    ) -> None:
        """
        Parameters
        ----------
        opener: `str`
            Left placeholder identifier.
        closer: `str`
            Right placeholder identifier.
        escape: `str`
            Escape string. 
            If opener or closer follows it, they are not identified.
        """
        if not isinstance(opener, str) or not opener:
            raise ValueError("'opener' should be a non-empty string")
        if not isinstance(closer, str) or not closer:
            raise ValueError("'closer' should be a non-empty string")
        if (isinstance(escape, str) and not escape) and escape is not None:
            raise ValueError("'escape' should be a non-empty string or None")
        if escape in {opener, closer}:
            raise ValueError("'escape' should not equal to 'opener' or 'closer'")
        
        self.opener: str = opener
        self.closer: str = closer
        self.escape: str | None = escape
        self.placeholders: list[Placeholder] = []
        for func in self.__placeholder_items__:
            ph = Placeholder(**func.__placeholder_args__)
            ph.process = partial(func, self)
            self.placeholders.append(ph) 
    
    def add_placeholder(self, ph: Placeholder, /) -> None:
        if not isinstance(ph, Placeholder):
            raise TypeError(
                f"Expected {Placeholder.__name__!r}, not {ph.__class__!r}"
            )

        ph.formatter = self
        self.placeholders.append(ph)

    async def process(self, name: str, depth: int) -> str | None:
        for ph in self.placeholders:
            if ph.pattern is None or ph.pattern.match(name):
                return await ph.func(name, depth)
        
        return None

    async def format(self, text: str) -> str:
        """
        Replace placeholders in the text.

        Parameters
        ----------
        text: `str`
            Text to format.
        """
        opener = self.opener
        closer = self.closer
        escape = self.escape
        opener_len = len(opener)
        closer_len = len(closer)
        escape_len = len(escape) if escape else 0
        same = self.opener == self.closer
        current = text
        prev_escape = False
        stack = []
        cache = {}
        index = 0

        while index < len(current):
            # check for escape string
            if escape and current[index : index + escape_len] == escape:
                # previously found escape string, keep only one
                if prev_escape:
                    current = ''.join((
                        current[: index - escape_len],
                        current[index:]
                    ))

                prev_escape = not prev_escape
                index += escape_len
            # check for opener 
            # if opener and closer are the same and there
            # is not opened brace, trigger closer 'elif'
            elif (
                current[index : index + opener_len] == opener 
                and not (same and stack)
            ):
                # save opener if escape string not found before
                if not prev_escape:
                    stack.append(index)
                else:
                    prev_escape = False
                    current = ''.join((
                        current[: index - escape_len],
                        current[index:]
                    ))

                index += opener_len
            # check for closer
            elif current[index : index + closer_len] == closer:
                # process placeholder if there is open brace
                # and escape string not found before
                if not prev_escape:
                    if stack:
                        open_index = stack.pop()
                        ph = current[open_index + opener_len : index]

                        # get cached value or process the placeholder
                        replacement = cache.get(ph)
                        if replacement is None:
                            value = await self.process(ph, len(stack))
                
                            # if value is None keep original placeholder
                            replacement = (
                                str(value) 
                                if value is not None else 
                                ''.join((opener, ph, closer))
                            )
                            cache[ph] = replacement
                        
                        # replace placeholder in the text
                        current = ''.join((
                            current[:open_index],
                            replacement,
                            current[index + closer_len :]
                        ))
                        index = open_index + len(replacement)
                    else:
                        index += closer_len
                else:
                    prev_escape = False
                    current = ''.join((
                        current[: index - len(escape)],
                        current[index:]
                    ))
            # skip any other character
            else:
                index += 1

        return current