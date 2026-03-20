"""
Shared constants and data structures for the itrading package.
"""

class SecurityType:
    """
    Represents the different security types supported by Interactive Brokers.
    The variable name is the description, and the value is the abbreviation.
    """
    Stock = "STK"
    Commodity = "CMDTY"
    Forex = "CASH"
    CFD = "CFD"
    Future = "FUT"
    Option = "OPT"
    Index = "IND"
