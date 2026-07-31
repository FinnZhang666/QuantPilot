class PortfolioCenterError(ValueError):
    pass


class ValidationError(PortfolioCenterError):
    pass


class PortfolioNotFound(PortfolioCenterError):
    pass


class HoldingNotFound(PortfolioCenterError):
    pass


class WatchlistNotFound(PortfolioCenterError):
    pass


class DuplicateSymbol(PortfolioCenterError):
    pass


class DuplicatePortfolioName(PortfolioCenterError):
    pass


class DuplicateDefaultPortfolio(PortfolioCenterError):
    pass


class PermissionDenied(PortfolioCenterError):
    pass
