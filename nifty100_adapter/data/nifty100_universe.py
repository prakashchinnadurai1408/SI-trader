"""Nifty 100 Universe Module.

Provides the Nifty 100 stock universe for the weekly backtester.
Contains constituent symbols, names, and sector classification.

Based on NSE Nifty 100 index constituents as of build date.
"""

from dataclasses import dataclass
from typing import List, Dict
from enum import Enum


class Sector(Enum):
    """Nifty 100 / Midcap universe sector classification."""
    FINANCIAL_SERVICES = "Financial Services"
    INFORMATION_TECHNOLOGY = "Information Technology"
    ENERGY = "Energy"
    POWER = "Power"
    CONSUMER_GOODS = "Consumer Goods"
    HEALTHCARE = "Healthcare"
    AUTOMOBILE = "Automobile"
    METALS = "Metals"
    CONSTRUCTION = "Construction"
    CONSUMER_DURABLES = "Consumer Durables"
    CEMENT = "Cement"
    TELECOM = "Telecom"
    PHARMA = "Pharma"
    CONSUMER_STAPLES = "Consumer Staples"
    OTHERS = "Others"
    MIDCAP = "Midcap"


@dataclass
class Stock:
    """Nifty 100 constituent."""
    symbol: str
    name: str
    sector: Sector
    market_cap_category: str  # "large_cap", "mid_cap"
    nifty_100_weight: float  # Index weight percentage


# Nifty 100 Constituents (as per SEBI/NSE classification).
# This list represents the Nifty 100 index constituents.
# In production, this would be fetched from NSE API or SEBI-certified data source.

NIFTY_100_CONSTITUENTS: List[Stock] = [
    # Large Cap stocks (existing Nifty 100)
    Stock("RELIANCE", "Reliance Industries", Sector.ENERGY, "large_cap", 8.5),
    Stock("TCS", "Tata Consultancy Services", Sector.INFORMATION_TECHNOLOGY, "large_cap", 7.2),
    Stock("HDFCBANK", "HDFC Bank", Sector.FINANCIAL_SERVICES, "large_cap", 6.8),
    Stock("ICICIBANK", "ICICI Bank", Sector.FINANCIAL_SERVICES, "large_cap", 5.1),
    Stock("SBIN", "State Bank of India", Sector.FINANCIAL_SERVICES, "large_cap", 3.2),
    Stock("BHARTIARTL", "Bharti Airtel", Sector.TELECOM, "large_cap", 3.1),
    Stock("HCLTECH", "HCL Technologies", Sector.INFORMATION_TECHNOLOGY, "large_cap", 1.2),
    Stock("INFY", "Infosys", Sector.INFORMATION_TECHNOLOGY, "large_cap", 1.1),
    Stock("ITC", "ITC Limited", Sector.CONSUMER_STAPLES, "large_cap", 1.8),
    Stock("KOTAKMAH", "Kotak Mahindra Bank", Sector.FINANCIAL_SERVICES, "large_cap", 1.5),
    Stock("ONGC", "ONGC", Sector.ENERGY, "large_cap", 1.8),
    Stock("IOC", "Indian Oil Corporation", Sector.ENERGY, "large_cap", 1.5),
    Stock("BPCL", "Bharat Petroleum", Sector.ENERGY, "large_cap", 0.8),
    Stock("MARUTI", "Maruti Suzuki", Sector.AUTOMOBILE, "large_cap", 2.1),
    Stock("TATASTEEL", "Tata Steel", Sector.METALS, "large_cap", 1.6),
    Stock("JSWSTEEL", "JSW Steel", Sector.METALS, "large_cap", 0.7),
    Stock("ACC", "ACC Limited", Sector.CEMENT, "large_cap", 0.4),
    Stock("AMBUJACEM", "Ambuja Cements", Sector.CEMENT, "large_cap", 0.3),
    Stock("NTPC", "NTPC", Sector.POWER, "large_cap", 1.0),
    Stock("POWERGRID", "Power Grid Corporation", Sector.POWER, "large_cap", 0.9),
    Stock("M&M", "Mahindra & Mahindra", Sector.AUTOMOBILE, "large_cap", 1.2),
    Stock("UPL", "UPL Limited", Sector.ENERGY, "large_cap", 0.6),
    Stock("SUNPHARMA", "Sun Pharma Industries", Sector.HEALTHCARE, "large_cap", 1.4),
    Stock("DRREDDY", "Dr. Reddy's Laboratories", Sector.HEALTHCARE, "large_cap", 0.9),
    Stock("CIPLA", "Cipla", Sector.HEALTHCARE, "large_cap", 0.5),
    Stock("COALINDIA", "Coal India", Sector.ENERGY, "large_cap", 1.1),
    Stock("ADANIENT", "Adani Enterprises", Sector.OTHERS, "large_cap", 0.8),
    Stock("ADANIPORTS", "Adani Ports", Sector.OTHERS, "large_cap", 0.5),
    Stock("Britannia", "Britannia Industries", Sector.CONSUMER_GOODS, "large_cap", 0.3),
    Stock("EicherMotors", "Eicher Motors", Sector.AUTOMOBILE, "large_cap", 0.5),
    Stock("HeroMotoCorp", "Hero MotoCorp", Sector.AUTOMOBILE, "large_cap", 0.4),
    Stock("Hindalco", "Hindalco Industries", Sector.METALS, "large_cap", 0.8),
    Stock("LART", "Larsen & Toubro", Sector.CONSTRUCTION, "large_cap", 1.1),
    Stock("M&M", "Mahindra & Mahindra", Sector.AUTOMOBILE, "large_cap", 1.2),
    Stock("Maruti", "Maruti Suzuki", Sector.AUTOMOBILE, "large_cap", 2.1),
    Stock("NTPC", "NTPC", Sector.POWER, "large_cap", 1.0),
    Stock("ONGC", "ONGC", Sector.ENERGY, "large_cap", 1.8),
    Stock("PowerGrid", "Power Grid Corporation", Sector.POWER, "large_cap", 0.9),
    Stock("Reliance", "Reliance Industries", Sector.ENERGY, "large_cap", 8.5),
    Stock("SBI", "State Bank of India", Sector.FINANCIAL_SERVICES, "large_cap", 3.2),
    Stock("Siemens", "Siemens", Sector.INFORMATION_TECHNOLOGY, "large_cap", 0.4),
    Stock("SBI", "State Bank of India", Sector.FINANCIAL_SERVICES, "large_cap", 3.2),
    Stock("SunPharma", "Sun Pharma", Sector.HEALTHCARE, "large_cap", 1.4),
    Stock("TCS", "Tata Consultancy Services", Sector.INFORMATION_TECHNOLOGY, "large_cap", 7.2),
    Stock("TataSteel", "Tata Steel", Sector.METALS, "large_cap", 1.6),
    Stock("TataMotors", "Tata Motors", Sector.AUTOMOBILE, "large_cap", 1.1),
    Stock("TechM", "Tech Mahindra", Sector.INFORMATION_TECHNOLOGY, "large_cap", 0.9),
    Stock("Titan", "Titan Company", Sector.CONSUMER_DURABLES, "large_cap", 0.5),
    Stock("UltraCement", "UltraTech Cement", Sector.CEMENT, "large_cap", 1.1),
    Stock("Usr", "United Spirits", Sector.CONSUMER_STAPLES, "large_cap", 0.4),
    Stock("Vedanta", "Vedanta", Sector.METALS, "large_cap", 0.9),
    Stock("Wipro", "Wipro", Sector.INFORMATION_TECHNOLOGY, "large_cap", 0.8),
    Stock("YesBank", "Yes Bank", Sector.FINANCIAL_SERVICES, "large_cap", 0.3),
    Stock("ZeeEnt", "Zee Entertainment Enterprises", Sector.OTHERS, "large_cap", 0.2),
]

# Note: This is a representative list. A complete Nifty 100 
# constituents list would contain exactly 100 stocks with 
# proper SEBI/NSE certification.

def get_nifty_100_universe() -> List[Stock]:
    """Get the complete Nifty 100 universe list."""
    return NIFTY_100_CONSTITUENTS


def get_symbols() -> List[str]:
    """Get just the symbol codes."""
    return [s.symbol for s in NIFTY_100_CONSTITUENTS]


def get_stock(symbol: str) -> Stock:
    """Get a specific stock by symbol."""
    for stock in NIFTY_100_CONSTITUENTS:
        if stock.symbol == symbol:
            return stock
    raise ValueError(f"Stock {symbol} not in Nifty 100 universe")


def count_by_sector() -> Dict[str, int]:
    """Count constituents by sector."""
    from collections import Counter
    return Counter(s.sector.value for s in NIFTY_100_CONSTITUENTS)


# Midcap universe - stocks outside Nifty 100 but with mid-cap market cap
# These are representative mid-cap stocks for the Midcap strategy
MIDCAP_UNIVERSE: List[Stock] = [
    Stock("ADANIGAS", "Adani Gas", Sector.OTHERS, "mid_cap", 0.3),
    Stock("APOLLOHOSP", "Apollo Hospitals", Sector.HEALTHCARE, "mid_cap", 0.4),
    Stock("BAJAJ-AUTO", "Bajaj Auto", Sector.AUTOMOBILE, "mid_cap", 0.5),
    Stock("BAJFINANCE", "Bajaj Finance", Sector.FINANCIAL_SERVICES, "mid_cap", 1.2),
    Stock("BERGEPAINT", "Berger Paints", Sector.CONSUMER_GOODS, "mid_cap", 0.3),
    Stock("CANBK", "Capital India Finance", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("COLPAL", "Colgate Palmolive", Sector.CONSUMER_STAPLES, "mid_cap", 0.3),
    Stock("DLF", "DLF Limited", Sector.CONSTRUCTION, "mid_cap", 0.4),
    Stock("EICHER", "Eicher Motors", Sector.AUTOMOBILE, "mid_cap", 0.5),
    Stock("GAIL", "GAIL India", Sector.ENERGY, "mid_cap", 0.4),
    Stock("GRASIM", "Grasim Industries", Sector.CONSTRUCTION, "mid_cap", 0.5),
    Stock("HPCL", "Hindustan Petroleum", Sector.ENERGY, "mid_cap", 0.3),
    Stock("ICICIPRULI", "ICICI Prudential", Sector.FINANCIAL_SERVICES, "mid_cap", 0.4),
    Stock("IFBIND", "IFB Industries", Sector.CONSUMER_DURABLES, "mid_cap", 0.3),
    Stock("INDUSINDBK", "IndusInd Bank", Sector.FINANCIAL_SERVICES, "mid_cap", 0.4),
    Stock("JINDALSTEL", "Jindal Steel", Sector.METALS, "mid_cap", 0.3),
    Stock("JSW", "JSW Steel", Sector.METALS, "mid_cap", 0.4),
    Stock("KOTAKMAH", "Kotak Mahindra Bank", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("LIC", "Life Insurance Corporation", Sector.FINANCIAL_SERVICES, "mid_cap", 0.5),
    Stock("MOTHERSUMI", "Motherson Sumi", Sector.AUTOMOBILE, "mid_cap", 0.3),
    Stock("MPHASIS", "Mphasis", Sector.INFORMATION_TECHNOLOGY, "mid_cap", 0.4),
    Stock("MRF", "MRF Limited", Sector.METALS, "mid_cap", 0.2),
    Stock("MUTHOOT", "Muthoot Finance", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("NAVA", "Nava", Sector.ENERGY, "mid_cap", 0.3),
    Stock("NBCC", "NBCC India", Sector.CONSTRUCTION, "mid_cap", 0.3),
    Stock("NMDC", "NMDC Limited", Sector.METALS, "mid_cap", 0.3),
    Stock("PEL", "Petronet LNG", Sector.ENERGY, "mid_cap", 0.3),
    Stock("PFC", "Power Finance Corporation", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("RECLTD", "REC Limited", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("SAIL", "Steel Authority", Sector.METALS, "mid_cap", 0.3),
    Stock("SRFCPF", "SRF Limited", Sector.CONSUMER_DURABLES, "mid_cap", 0.3),
    Stock("TATACONSUM", "Tata Consumer", Sector.CONSUMER_STAPLES, "mid_cap", 0.4),
    Stock("TATAELXSI", "Tata Elxsi", Sector.INFORMATION_TECHNOLOGY, "mid_cap", 0.3),
    Stock("TCI", "TCI Express", Sector.AUTOMOBILE, "mid_cap", 0.2),
    Stock("TEXRAIL", "Texrail", Sector.ENERGY, "mid_cap", 0.3),  # placeholder
    Stock("TORNTPH", "Torrent Power", Sector.POWER, "mid_cap", 0.3),
    Stock("UBL", "Union Bank of India", Sector.FINANCIAL_SERVICES, "mid_cap", 0.3),
    Stock("WOCKPHARMA", "Wockhardt", Sector.HEALTHCARE, "mid_cap", 0.3),
    Stock("YESBANK", "Yes Bank", Sector.FINANCIAL_SERVICES, "mid_cap", 0.2),
]


def get_midcap_universe() -> List[Stock]:
    """Get the midcap universe list."""
    return MIDCAP_UNIVERSE


def get_all_universe() -> List[Stock]:
    """Get combined Nifty 100 + Midcap universe."""
    return NIFTY_100_CONSTITUENTS + MIDCAP_UNIVERSE


def get_symbols_by_market_cap(cap_category: str) -> List[str]:
    """Get symbols filtered by market cap category."""
    all_stocks = get_all_universe()
    return [s.symbol for s in all_stocks if s.market_cap_category == cap_category]


def count_by_market_cap() -> Dict[str, int]:
    """Count constituents by market cap category."""
    from collections import Counter
    return Counter(s.market_cap_category for s in get_all_universe())


# Sector mapping from symbol name (for quick lookup)
SECTOR_MAP = {
    "RELIANCE": Sector.ENERGY,
    "TCS": Sector.INFORMATION_TECHNOLOGY,
    "HDFCBANK": Sector.FINANCIAL_SERVICES,
    "ICICIBANK": Sector.FINANCIAL_SERVICES,
    "SBIN": Sector.FINANCIAL_SERVICES,
    "BHARTIARTL": Sector.TELECOM,
    "MARUTI": Sector.AUTOMOBILE,
    "INFY": Sector.INFORMATION_TECHNOLOGY,
    "ITC": Sector.CONSUMER_STAPLES,
    "KOTAKMAH": Sector.FINANCIAL_SERVICES,
    "ONGC": Sector.ENERGY,
    "IOC": Sector.ENERGY,
    "BPCL": Sector.ENERGY,
    "TATASTEEL": Sector.METALS,
    "JSWSTEEL": Sector.METALS,
    "ACC": Sector.CEMENT,
    "AMBUJACEM": Sector.CEMENT,
    "NTPC": Sector.POWER,
    "POWERGRID": Sector.POWER,
    "SUNPHARMA": Sector.HEALTHCARE,
    "DRREDDY": Sector.HEALTHCARE,
    "CIPLA": Sector.HEALTHCARE,
}


def get_sector(symbol: str) -> Sector:
    """Get sector for a Nifty 100 / Midcap symbol."""
    if symbol in SECTOR_MAP:
        return SECTOR_MAP[symbol]
    return Sector.OTHERS