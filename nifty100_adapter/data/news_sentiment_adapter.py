"""News Sentiment Data Adapter for SI-Trader.

Provides news sentiment analysis for Indian stocks.

Data Sources:
- NewsAPI.org
- Google News
- Press Information Bureau (PIB)
- Company press releases

Parameters Covered:
- historical_news_sentiment (Score, weight=4, daily)
- company_news (Advisory, weight=0, daily - disabled)
- company_analytics (Advisory, weight=0, weekly - disabled)
- customer_feedback (Advisory, weight=0, monthly - disabled)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
import asyncio
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class NewsArticle:
    """Single news article."""
    title: str
    description: str
    content: str
    source: str
    published_at: str
    url: str
    sentiment_score: float = 0.0  # -1 to 1
    sentiment_label: str = "NEUTRAL"  # POSITIVE, NEGATIVE, NEUTRAL
    relevance_score: float = 0.0  # 0 to 1


@dataclass
class NewsSentimentResult:
    """News sentiment analysis result."""
    symbol: str
    company_name: str
    overall_sentiment: float  # -1 to 1
    sentiment_label: str  # POSITIVE, NEGATIVE, NEUTRAL
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    avg_relevance: float
    key_themes: List[str] = field(default_factory=list)
    recent_headlines: List[str] = field(default_factory=list)
    calculated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if self.overall_sentiment > 0.1:
            self.sentiment_label = "POSITIVE"
        elif self.overall_sentiment < -0.1:
            self.sentiment_label = "NEGATIVE"
        else:
            self.sentiment_label = "NEUTRAL"


class NewsSentimentAdapter:
    """News Sentiment Data Adapter.

    Fetches news articles and performs sentiment analysis for Indian stocks.

    Parameters Covered:
    - historical_news_sentiment (Score, weight=4, daily)
    - company_news (Advisory, weight=0, daily - disabled)
    - company_analytics (Advisory, weight=0, weekly - disabled)
    - customer_feedback (Advisory, weight=0, monthly - disabled)
    """

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://newsapi.org/v2"):
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self.cache_ttl_hours = 6  # News cache for 6 hours

        logger.info("NewsSentimentAdapter initialized")

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _fetch(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Fetch data from News API with retry logic."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            async with self.session.get(url, params=params, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 429:
                    logger.warning("News API rate limit exceeded, waiting...")
                    await asyncio.sleep(2)
                    return await self._fetch(url, params)
                else:
                    logger.error(f"News API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"News API request failed: {e}")
            return None

    async def get_news_articles(self, symbol: str,
                                company_name: Optional[str] = None,
                                days: int = 7) -> List[NewsArticle]:
        """Get news articles for a stock.

        Args:
            symbol: Stock symbol (e.g., RELIANCE)
            company_name: Company name for better search
            days: Number of days to look back

        Returns:
            List of NewsArticle objects
        """
        cache_key = f"news_{symbol}_{days}"

        if cache_key in self._cache and cache_key in self._cache_ttl:
            if datetime.now() < self._cache_ttl[cache_key]:
                return self._cache[cache_key]

        # Build search query
        query = company_name if company_name else symbol
        query = f"{query} stock OR share OR NSE OR BSE OR equity"

        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        url = f"{self.base_url}/everything"
        params = {
            "q": query,
            "from": from_date,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 50,
        }

        if self.api_key:
            params["apiKey"] = self.api_key

        data = await self._fetch(url, params)
        if not data or "articles" not in data:
            logger.warning(f"No news articles for {symbol}")
            return []

        articles = []
        for item in data.get("articles", []):
            try:
                article = NewsArticle(
                    title=item.get("title", ""),
                    description=item.get("description", "") or "",
                    content=item.get("content", "") or "",
                    source=item.get("source", {}).get("name", "Unknown"),
                    published_at=item.get("publishedAt", ""),
                    url=item.get("url", ""),
                    sentiment_score=0.0,  # Will be calculated below
                    sentiment_label="NEUTRAL",
                    relevance_score=0.8,  # Default relevance
                )
                articles.append(article)
            except Exception as e:
                logger.warning(f"Error parsing article: {e}")
                continue

        # Perform sentiment analysis
        articles = self._analyze_sentiment(articles, symbol, company_name)

        # Cache result
        self._cache[cache_key] = articles
        self._cache_ttl[cache_key] = datetime.now() + timedelta(hours=self.cache_ttl_hours)

        return articles

    def _analyze_sentiment(self, articles: List[NewsArticle],
                           symbol: str,
                           company_name: Optional[str] = None) -> List[NewsArticle]:
        """Simple sentiment analysis using keyword matching.

        In production, this would use NLP models like VADER, TextBlob, or transformer models.
        """
        positive_keywords = [
            "profit", "growth", "gain", "rise", "surge", "boost", "rally",
            "outperform", "beat", "exceed", "strong", "positive", "bullish",
            "upgrade", "buy", "recommend", "expansion", "acquisition", "deal",
            "partnership", "contract", "order", "win", "success", "milestone",
        ]

        negative_keywords = [
            "loss", "decline", "drop", "fall", "crash", "slump", "downturn",
            "underperform", "miss", "below", "weak", "negative", "bearish",
            "downgrade", "sell", "avoid", "crisis", "scandal", "fraud",
            "investigation", "penalty", "fine", "lawsuit", "legal",
        ]

        for article in articles:
            text = f"{article.title} {article.description} {article.content}".lower()
            positive_count = sum(1 for kw in positive_keywords if kw in text)
            negative_count = sum(1 for kw in negative_keywords if kw in text)

            total = positive_count + negative_count
            if total > 0:
                article.sentiment_score = (positive_count - negative_count) / total
            else:
                article.sentiment_score = 0.0

            if article.sentiment_score > 0.1:
                article.sentiment_label = "POSITIVE"
            elif article.sentiment_score < -0.1:
                article.sentiment_label = "NEGATIVE"
            else:
                article.sentiment_label = "NEUTRAL"

            # Relevance based on symbol/company name mentions
            symbol_lower = symbol.lower()
            company_lower = (company_name or "").lower()
            text_lower = text

            relevance = 0.0
            if symbol_lower in text_lower:
                relevance += 0.4
            if company_lower and company_lower in text_lower:
                relevance += 0.4
            if "stock" in text_lower or "share" in text_lower or "nse" in text_lower or "bse" in text_lower:
                relevance += 0.2

            article.relevance_score = min(1.0, relevance)

        return articles

    async def calculate_sentiment_score(self, symbol: str,
                                        company_name: Optional[str] = None) -> Optional[NewsSentimentResult]:
        """Calculate sentiment score for a symbol.

        Args:
            symbol: Stock symbol
            company_name: Company name for better search

        Returns:
            NewsSentimentResult or None
        """
        articles = await self.get_news_articles(symbol, company_name)

        if not articles:
            return NewsSentimentResult(
                symbol=symbol,
                company_name=company_name or symbol,
                overall_sentiment=0.0,
                sentiment_label="NEUTRAL",
                article_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                avg_relevance=0.0,
            )

        total_articles = len(articles)
        positive_count = sum(1 for a in articles if a.sentiment_label == "POSITIVE")
        negative_count = sum(1 for a in articles if a.sentiment_label == "NEGATIVE")
        neutral_count = sum(1 for a in articles if a.sentiment_label == "NEUTRAL")

        # Weighted sentiment by relevance
        weighted_sum = sum(a.sentiment_score * a.relevance_score for a in articles)
        relevance_sum = sum(a.relevance_score for a in articles)

        overall_sentiment = weighted_sum / relevance_sum if relevance_sum > 0 else 0.0
        avg_relevance = relevance_sum / total_articles if total_articles > 0 else 0.0

        # Extract key themes and headlines
        key_themes = list(set(
            word for article in articles
            for word in article.title.lower().split()
            if len(word) > 4
        ))[:10]

        recent_headlines = [a.title for a in articles[:5]]

        return NewsSentimentResult(
            symbol=symbol,
            company_name=company_name or symbol,
            overall_sentiment=round(overall_sentiment, 3),
            sentiment_label=articles[0].sentiment_label if articles else "NEUTRAL",
            article_count=total_articles,
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            avg_relevance=round(avg_relevance, 3),
            key_themes=key_themes,
            recent_headlines=recent_headlines,
        )

    async def get_multiple_sentiments(self, symbols: List[str],
                                      company_names: Optional[Dict[str, str]] = None) -> Dict[str, NewsSentimentResult]:
        """Get sentiment scores for multiple symbols."""
        results = {}
        for symbol in symbols:
            try:
                company_name = company_names.get(symbol) if company_names else None
                result = await self.calculate_sentiment_score(symbol, company_name)
                if result:
                    results[symbol] = result
            except Exception as e:
                logger.error(f"Error calculating sentiment for {symbol}: {e}")
                continue
        return results