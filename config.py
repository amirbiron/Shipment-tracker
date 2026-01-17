"""
Configuration module for Shipment Tracker Bot
Loads environment variables and provides typed configuration
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv
import pytz

# Load environment variables
load_dotenv()


@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str
    
    @classmethod
    def from_env(cls) -> 'TelegramConfig':
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")
        return cls(bot_token=bot_token)


@dataclass
class MongoDBConfig:
    """MongoDB configuration"""
    uri: str
    database_name: str = "shipment_tracker"
    
    @classmethod
    def from_env(cls) -> 'MongoDBConfig':
        uri = os.getenv('MONGODB_URI')
        if not uri:
            raise ValueError("MONGODB_URI not set in environment")
        return cls(
            uri=uri,
            database_name=os.getenv('MONGODB_DATABASE', 'shipment_tracker')
        )


@dataclass
class TrackingAPIConfig:
    """17TRACK API configuration"""
    api_key: str
    base_url: str = "https://api.17track.net/track/v1"
    rate_limit: int = 3  # requests per second
    
    @classmethod
    def from_env(cls) -> 'TrackingAPIConfig':
        api_key = os.getenv('TRACKING_API_KEY')
        if not api_key:
            raise ValueError("TRACKING_API_KEY not set in environment")
        return cls(api_key=api_key)


@dataclass
class AppConfig:
    """Application configuration"""
    environment: str
    log_level: str
    timezone: pytz.timezone
    
    # Rate limiting
    max_active_shipments_per_user: int
    refresh_cooldown_minutes: int
    add_rate_limit_per_minute: int
    
    # Polling settings
    polling_interval_minutes: int
    
    @classmethod
    def from_env(cls) -> 'AppConfig':
        timezone_str = os.getenv('TIMEZONE', 'Asia/Jerusalem')
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.UTC
        
        return cls(
            environment=os.getenv('ENVIRONMENT', 'production'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            timezone=tz,
            max_active_shipments_per_user=int(os.getenv('MAX_ACTIVE_SHIPMENTS_PER_USER', '30')),
            refresh_cooldown_minutes=int(os.getenv('REFRESH_COOLDOWN_MINUTES', '10')),
            add_rate_limit_per_minute=int(os.getenv('ADD_RATE_LIMIT_PER_MINUTE', '5')),
            polling_interval_minutes=int(os.getenv('POLLING_INTERVAL_MINUTES', '2'))
        )


@dataclass
class Config:
    """Main configuration container"""
    telegram: TelegramConfig
    mongodb: MongoDBConfig
    tracking_api: TrackingAPIConfig
    app: AppConfig
    
    @classmethod
    def load(cls) -> 'Config':
        """Load all configuration from environment"""
        return cls(
            telegram=TelegramConfig.from_env(),
            mongodb=MongoDBConfig.from_env(),
            tracking_api=TrackingAPIConfig.from_env(),
            app=AppConfig.from_env()
        )


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance"""
    global _config
    if _config is None:
        _config = Config.load()
    return _config
