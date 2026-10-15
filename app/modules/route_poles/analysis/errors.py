class AnalysisError(Exception):
    """The routes file or the city can't be analysed.

    The message is shown to the user (Portuguese), so it says what to fix.
    """


class SourceError(AnalysisError):
    """An external source (IBGE, geodata-br) failed or answered garbage."""
