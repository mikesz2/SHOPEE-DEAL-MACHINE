from datetime import datetime
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Source(Base):
    __tablename__ = 'sources'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    chat_ref: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    learned_weight: Mapped[float] = mapped_column(Float, default=1.0)
    detected_count: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    converted_count: Mapped[int] = mapped_column(Integer, default=0)
    commission_total: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (
        UniqueConstraint('shop_id', 'item_id', name='uq_product_identity'),
        Index('ix_products_updated', 'updated_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shop_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(80), default='outros', index=True)
    shop_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    sales: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission: Mapped[float | None] = mapped_column(Float, nullable=True)
    offer_period_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PriceSnapshot(Base):
    __tablename__ = 'price_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class OfferEvent(Base):
    __tablename__ = 'offer_events'
    __table_args__ = (
        UniqueConstraint('product_id', 'source_type', 'source_ref', 'source_message_id', name='uq_offer_source_message'),
        Index('ix_offer_queue', 'status', 'final_score', 'created_at'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    detected_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    deal_score: Mapped[float] = mapped_column(Float, default=0)
    trend_score: Mapped[float] = mapped_column(Float, default=0)
    final_score: Mapped[float] = mapped_column(Float, default=0, index=True)
    source_weight_snapshot: Mapped[float] = mapped_column(Float, default=1.0)
    status: Mapped[str] = mapped_column(String(32), default='queued', index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    product: Mapped[Product] = relationship()

    @property
    def score(self) -> float:  # compatibility with V1 frontend/tests
        return self.final_score


class Publication(Base):
    __tablename__ = 'publications'
    __table_args__ = (Index('ix_publication_tracking', 'tracking_key'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    offer_event_id: Mapped[int] = mapped_column(ForeignKey('offer_events.id'), index=True)
    telegram_chat: Mapped[str] = mapped_column(String(255))
    telegram_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default='pending', index=True)
    template_variant: Mapped[str] = mapped_column(String(40), default='default', index=True)
    tracking_key: Mapped[str] = mapped_column(String(64), unique=True)
    affiliate_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    caption: Mapped[str] = mapped_column(Text, default='')
    price_at_publish: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_rate_at_publish: Mapped[float | None] = mapped_column(Float, nullable=True)
    conversion_count: Mapped[int] = mapped_column(Integer, default=0)
    commission_total: Mapped[float] = mapped_column(Float, default=0.0)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    offer_event: Mapped[OfferEvent] = relationship()


class Conversion(Base):
    __tablename__ = 'conversions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversion_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey('publications.id'), nullable=True, index=True)
    utm_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_commission: Mapped[float] = mapped_column(Float, default=0.0)
    orders_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0)
    raw_json: Mapped[str] = mapped_column(Text, default='{}')
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RadarInbox(Base):
    __tablename__ = 'radar_inbox'
    __table_args__ = (UniqueConstraint('source_ref', 'message_id', 'url', name='uq_radar_inbox'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ref: Mapped[str] = mapped_column(String(255), index=True)
    message_id: Mapped[str] = mapped_column(String(120))
    url: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(32), default='pending', index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SourceCursor(Base):
    __tablename__ = 'source_cursors'
    source_ref: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_message_id: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = 'app_settings'
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    __table_args__ = (Index('ix_audit_created_severity', 'created_at', 'severity'),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(16), default='info', index=True)
    actor: Mapped[str] = mapped_column(String(80), default='system')
    message: Mapped[str] = mapped_column(Text)
    context_json: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class DiscoveryMemory(Base):
    __tablename__ = 'discovery_memory'
    __table_args__ = (UniqueConstraint('product_id', name='uq_discovery_product'), Index('ix_discovery_last_seen','last_seen_at'))
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    times_seen: Mapped[int] = mapped_column(Integer, default=1)
    query_hits: Mapped[int] = mapped_column(Integer, default=1)
    unique_queries: Mapped[int] = mapped_column(Integer, default=1)
    unique_sorts: Mapped[int] = mapped_column(Integer, default=1)
    novelty_score: Mapped[float] = mapped_column(Float, default=100)
    best_score: Mapped[float] = mapped_column(Float, default=0)
    last_query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_sort: Mapped[int | None] = mapped_column(Integer, nullable=True)
