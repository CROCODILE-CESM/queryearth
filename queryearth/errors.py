"""Error classes the design names (reference/decisions.md, "Error classes").

Where the design only says that something "is an error", the engine raises a
plain ValueError or TypeError with a message that names the problem.
"""

__all__ = ["DuplicateCodeError", "LoadError", "UnknownNameError"]


class DuplicateCodeError(ValueError):
    """A code the Registry already holds was registered again (section 12.3)."""


class UnknownNameError(KeyError):
    """An undeclared axis, facet, dimension, product or region name.

    A misspelt name would otherwise look like "no known issues", so the engine
    refuses it in rules and queries alike (sections 4.6 and 4.7).
    """

    def __str__(self) -> str:
        # KeyError quotes its argument, which would wrap the message in quotes
        if len(self.args) == 1:
            return str(self.args[0])
        return super().__str__()


class LoadError(ValueError):
    """A pack or FeatureCollection failed the loader checks (section 5.3).

    .problems lists each, naming its file, the feature's position and its code.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))
