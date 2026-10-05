from pydantic import BaseModel, Field


class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    chat_ref: str = Field(min_length=1, max_length=255)
    active: bool = True
    weight: float = Field(default=1.0, ge=0.1, le=5.0)


class RuntimeSettings(BaseModel):
    auto_publish: bool = False
    telegram_publish_enabled: bool = True
    whatsapp_enabled: bool = False
    whatsapp_groups: list[str] = Field(default_factory=list, max_length=30)
    whatsapp_interval_seconds: int = Field(default=30, ge=10, le=120)
    discovery_expand_keywords: bool = True
    discovery_max_candidates: int = Field(default=120, ge=1, le=500)
    discovery_shop_limit: int = Field(default=2, ge=1, le=50)
    radar_pages: int = Field(default=5, ge=1, le=10)
    discovery_max_queries: int = Field(default=120, ge=12, le=300)
    discovery_concurrency: int = Field(default=6, ge=1, le=12)
    discovery_sort_modes: str = '1,2,3,4,5'
    max_offer_age_hours: int = Field(default=6, ge=1, le=72)
    require_quality_data: bool = True
    post_interval_minutes: int = Field(default=25, ge=1, le=1440)
    breaking_enabled: bool = True
    breaking_min_score: float = Field(default=92, ge=0, le=100)
    breaking_min_trend: float = Field(default=55, ge=0, le=100)
    breaking_min_interval_minutes: int = Field(default=5, ge=1, le=180)

    radar_interval_minutes: int = Field(default=15, ge=3, le=1440)
    conversion_sync_minutes: int = Field(default=30, ge=5, le=1440)
    min_score: float = Field(default=62, ge=0, le=100)
    min_discount: float = Field(default=10, ge=0, le=100)
    min_rating: float = Field(default=4.2, ge=0, le=5)
    min_sales: int = Field(default=20, ge=0)
    min_commission_rate: float = Field(default=0, ge=0, le=100)
    cooldown_days: int = Field(default=7, ge=0, le=365)
    similarity_cooldown_hours: int = Field(default=12, ge=0, le=720)
    similarity_threshold: float = Field(default=0.72, ge=0, le=1)

    radar_keywords: str = 'eletrônicos,casa,cozinha,beleza,gamer,celular,ferramentas'
    max_products_per_keyword: int = Field(default=12, ge=1, le=50)

    allowed_templates: list[str] = ['default', 'urgente', 'clean']
    template_learning: bool = True
    source_learning: bool = True
    smart_schedule: bool = True

    blocked_keywords: str = 'réplica,conta,assinatura,key,+18'
    priority_keywords: str = 'samsung,xiaomi,lenovo,mondial,stanley,philips'
    blocked_shop_ids: str = ''

    category_daily_limits: dict[str, int] = {
        'eletronicos': 12, 'casa': 10, 'cozinha': 10, 'beleza': 8,
        'gamer': 8, 'ferramentas': 8, 'moda': 6, 'outros': 10,
    }
    max_same_category_consecutive: int = Field(default=2, ge=1, le=20)

    quiet_hours_enabled: bool = False
    quiet_start_hour: int = Field(default=23, ge=0, le=23)
    quiet_end_hour: int = Field(default=7, ge=0, le=23)

    max_publish_attempts: int = Field(default=5, ge=1, le=20)
    retry_base_seconds: int = Field(default=60, ge=5, le=3600)
    max_price_increase_pct: float = Field(default=20, ge=0, le=500)
    event_retention_days: int = Field(default=90, ge=7, le=730)
    snapshot_retention_days: int = Field(default=60, ge=7, le=730)
    failed_publication_retention_days: int = Field(default=30, ge=7, le=365)

    # Enterprise guardrails
    max_queue_depth: int = Field(default=2500, ge=50, le=100000)
    alert_queue_depth: int = Field(default=300, ge=10, le=50000)
    circuit_breaker_failures: int = Field(default=8, ge=2, le=100)
    circuit_breaker_cooldown_minutes: int = Field(default=10, ge=1, le=240)
    dashboard_refresh_seconds: int = Field(default=15, ge=5, le=120)
    audit_retention_days: int = Field(default=180, ge=30, le=3650)


class ManualIngest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    source_ref: str = 'manual'


class BulkOfferAction(BaseModel):
    offer_ids: list[int] = Field(min_length=1, max_length=200)
    action: str = Field(pattern='^(retry|reject)$')
