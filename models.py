"""
Data models for Shipment Tracker Bot
Defines all data structures used in the application
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from bson import ObjectId


class ShipmentState(str, Enum):
    """Shipment state enum"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class StatusNorm(str, Enum):
    """Normalized status enum for better handling"""
    INFO_RECEIVED = "INFO_RECEIVED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED_SORTING_CENTER = "ARRIVED_SORTING_CENTER"
    ARRIVED_DESTINATION = "ARRIVED_DESTINATION"
    CUSTOMS = "CUSTOMS"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    EXCEPTION = "EXCEPTION"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


# Hebrew translations for statuses
STATUS_TRANSLATIONS_HE: Dict[StatusNorm, str] = {
    StatusNorm.INFO_RECEIVED: "מידע התקבל",
    StatusNorm.IN_TRANSIT: "בדרך",
    StatusNorm.ARRIVED_SORTING_CENTER: "הגיע למרכז מיון",
    StatusNorm.ARRIVED_DESTINATION: "הגיע ליעד",
    StatusNorm.CUSTOMS: "בשחרור ממכס",
    StatusNorm.OUT_FOR_DELIVERY: "יצא לחלוקה",
    StatusNorm.DELIVERED: "נמסר",
    StatusNorm.EXCEPTION: "חריגה/בעיה במשלוח",
    StatusNorm.EXPIRED: "פג תוקף",
    StatusNorm.UNKNOWN: "לא ידוע"
}


@dataclass
class CarrierCandidate:
    """Carrier candidate from detection"""
    code: str
    name: str
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "code": self.code,
            "name": self.name
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'CarrierCandidate':
        return cls(
            code=data['code'],
            name=data['name']
        )


@dataclass
class ShipmentEvent:
    """Single tracking event"""
    status_raw: str
    status_norm: StatusNorm
    timestamp: Optional[datetime] = None
    location: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status_raw": self.status_raw,
            "status_norm": self.status_norm.value,
            "timestamp": self.timestamp,
            "location": self.location,
            "raw": self.raw
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ShipmentEvent':
        timestamp = data.get('timestamp')
        if timestamp and not isinstance(timestamp, datetime):
            try:
                timestamp = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                timestamp = None
        
        return cls(
            status_raw=data.get('status_raw', ''),
            status_norm=StatusNorm(data.get('status_norm', 'UNKNOWN')),
            timestamp=timestamp,
            location=data.get('location'),
            raw=data.get('raw')
        )


@dataclass
class Shipment:
    """Shipment entity - global tracking information"""
    tracking_number: str
    carrier_code: str
    carrier_candidates: List[CarrierCandidate] = field(default_factory=list)
    state: ShipmentState = ShipmentState.ACTIVE
    last_event: Optional[ShipmentEvent] = None
    last_event_hash: Optional[str] = None
    last_check_at: Optional[datetime] = None
    next_check_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[ObjectId] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        doc = {
            "tracking_number": self.tracking_number,
            "carrier_code": self.carrier_code,
            "carrier_candidates": [c.to_dict() for c in self.carrier_candidates],
            "state": self.state.value,
            "last_event": self.last_event.to_dict() if self.last_event else None,
            "last_event_hash": self.last_event_hash,
            "last_check_at": self.last_check_at,
            "next_check_at": self.next_check_at,
            "delivered_at": self.delivered_at,
            "updated_at": self.updated_at,
            "created_at": self.created_at
        }
        if self.id:
            doc["_id"] = self.id
        return doc
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Shipment':
        """Create from MongoDB document"""
        return cls(
            tracking_number=data['tracking_number'],
            carrier_code=data['carrier_code'],
            carrier_candidates=[CarrierCandidate.from_dict(c) for c in data.get('carrier_candidates', [])],
            state=ShipmentState(data['state']),
            last_event=ShipmentEvent.from_dict(data['last_event']) if data.get('last_event') else None,
            last_event_hash=data.get('last_event_hash'),
            last_check_at=data.get('last_check_at'),
            next_check_at=data.get('next_check_at'),
            delivered_at=data.get('delivered_at'),
            updated_at=data['updated_at'],
            created_at=data['created_at'],
            id=data.get('_id')
        )


@dataclass
class Subscription:
    """User subscription to a shipment"""
    user_id: int
    shipment_id: ObjectId
    item_name: str
    muted: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: Optional[ObjectId] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MongoDB document"""
        doc = {
            "user_id": self.user_id,
            "shipment_id": self.shipment_id,
            "item_name": self.item_name,
            "muted": self.muted,
            "created_at": self.created_at
        }
        if self.id:
            doc["_id"] = self.id
        return doc
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Subscription':
        """Create from MongoDB document"""
        return cls(
            user_id=data['user_id'],
            shipment_id=data['shipment_id'],
            item_name=data['item_name'],
            muted=data.get('muted', False),
            created_at=data['created_at'],
            id=data.get('_id')
        )
