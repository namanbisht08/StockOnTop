from abc import ABC, abstractmethod
from datetime import date
from typing import List

import pandas as pd
from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    price: float
    timestamp: date


class CorporateEvent(BaseModel):
    symbol: str
    date: date
    event_type: str
    description: str


class NewsArticle(BaseModel):
    symbol: str
    title: str
    url: str
    source: str
    published_at: date
    retrieved_at: date
    query: str


class MarketDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(
        self,
        symbol: str,
        start: date,
        end: date,
        interval: str = "1d",
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        pass

    @abstractmethod
    def get_index_data(
        self, index: str, start: date, end: date, interval: str = "1d"
    ) -> pd.DataFrame:
        pass


class NewsProvider(ABC):
    @abstractmethod
    def search(
        self,
        company_name: str,
        symbol: str,
        lookback_days: int = 7,
    ) -> List[NewsArticle]:
        pass


class CorporateEventsProvider(ABC):
    @abstractmethod
    def get_events(
        self,
        symbol: str,
        lookback_days: int = 7,
    ) -> List[CorporateEvent]:
        pass
