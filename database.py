"""
Database module for MongoDB operations
Handles all database interactions using PyMongo Async
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId
from pymongo import AsyncMongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from models import Shipment, Subscription, ShipmentState
from config import get_config

logger = logging.getLogger(__name__)


class Database:
    """MongoDB database handler with async support"""
    
    def __init__(self):
        self.client: Optional[AsyncMongoClient] = None
        self.db = None
        self.shipments = None
        self.subscriptions = None
        self.shipment_events = None
    
    async def connect(self):
        """Connect to MongoDB and create indexes"""
        config = get_config()
        
        logger.info(f"Connecting to MongoDB...")
        self.client = AsyncMongoClient(config.mongodb.uri)
        self.db = self.client[config.mongodb.database_name]
        
        # Collections
        self.shipments = self.db.shipments
        self.subscriptions = self.db.subscriptions
        self.shipment_events = self.db.shipment_events
        
        # Create indexes
        await self._create_indexes()
        
        logger.info("MongoDB connected successfully")
    
    async def disconnect(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB disconnected")
    
    async def _create_indexes(self):
        """Create all necessary indexes"""
        # Shipments indexes
        await self.shipments.create_index(
            [("state", ASCENDING), ("next_check_at", ASCENDING)],
            name="polling_index"
        )
        await self.shipments.create_index(
            [("tracking_number", ASCENDING), ("carrier_code", ASCENDING)],
            unique=True,
            name="unique_shipment"
        )
        
        # Subscriptions indexes
        await self.subscriptions.create_index(
            [("user_id", ASCENDING)],
            name="user_subscriptions"
        )
        await self.subscriptions.create_index(
            [("shipment_id", ASCENDING)],
            name="shipment_subscribers"
        )
        await self.subscriptions.create_index(
            [("user_id", ASCENDING), ("shipment_id", ASCENDING)],
            unique=True,
            name="unique_subscription"
        )
        
        # Shipment events indexes (optional collection)
        await self.shipment_events.create_index(
            [("shipment_id", ASCENDING), ("timestamp", DESCENDING)],
            name="shipment_timeline"
        )
        
        logger.info("Database indexes created")
    
    # === Shipment Operations ===
    
    async def create_shipment(self, shipment: Shipment) -> ObjectId:
        """Create a new shipment"""
        try:
            result = await self.shipments.insert_one(shipment.to_dict())
            logger.info(f"Created shipment: {shipment.tracking_number}")
            return result.inserted_id
        except DuplicateKeyError:
            # Shipment already exists
            existing = await self.get_shipment_by_tracking(
                shipment.tracking_number,
                shipment.carrier_code
            )
            if existing:
                return existing.id
            raise
    
    async def get_shipment(self, shipment_id: ObjectId) -> Optional[Shipment]:
        """Get shipment by ID"""
        doc = await self.shipments.find_one({"_id": shipment_id})
        if doc:
            return Shipment.from_dict(doc)
        return None
    
    async def get_shipment_by_tracking(
        self,
        tracking_number: str,
        carrier_code: str
    ) -> Optional[Shipment]:
        """Get shipment by tracking number and carrier"""
        doc = await self.shipments.find_one({
            "tracking_number": tracking_number,
            "carrier_code": carrier_code
        })
        if doc:
            return Shipment.from_dict(doc)
        return None
    
    async def update_shipment(self, shipment: Shipment):
        """Update existing shipment"""
        shipment.updated_at = datetime.utcnow()
        await self.shipments.update_one(
            {"_id": shipment.id},
            {"$set": shipment.to_dict()}
        )
        logger.info(f"Updated shipment: {shipment.tracking_number}")
    
    async def get_shipments_due_for_check(self, limit: int = 100) -> List[Shipment]:
        """Get shipments that need to be checked now"""
        now = datetime.utcnow()
        cursor = self.shipments.find({
            "state": ShipmentState.ACTIVE.value,
            "next_check_at": {"$lte": now}
        }).limit(limit)
        
        shipments = []
        async for doc in cursor:
            shipments.append(Shipment.from_dict(doc))
        
        return shipments
    
    async def archive_shipment(self, shipment_id: ObjectId):
        """Archive a shipment (after delivery)"""
        await self.shipments.update_one(
            {"_id": shipment_id},
            {
                "$set": {
                    "state": ShipmentState.ARCHIVED.value,
                    "delivered_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info(f"Archived shipment: {shipment_id}")
    
    async def reactivate_shipment(self, shipment_id: ObjectId):
        """Reactivate an archived shipment"""
        await self.shipments.update_one(
            {"_id": shipment_id},
            {
                "$set": {
                    "state": ShipmentState.ACTIVE.value,
                    "next_check_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                },
                "$unset": {"delivered_at": ""}
            }
        )
        logger.info(f"Reactivated shipment: {shipment_id}")
    
    # === Subscription Operations ===
    
    async def create_subscription(self, subscription: Subscription) -> ObjectId:
        """Create a new subscription"""
        try:
            result = await self.subscriptions.insert_one(subscription.to_dict())
            logger.info(f"Created subscription for user {subscription.user_id}")
            return result.inserted_id
        except DuplicateKeyError:
            # Subscription already exists
            existing = await self.get_subscription(
                subscription.user_id,
                subscription.shipment_id
            )
            if existing:
                return existing.id
            raise
    
    async def get_subscription(
        self,
        user_id: int,
        shipment_id: ObjectId
    ) -> Optional[Subscription]:
        """Get specific subscription"""
        doc = await self.subscriptions.find_one({
            "user_id": user_id,
            "shipment_id": shipment_id
        })
        if doc:
            return Subscription.from_dict(doc)
        return None
    
    async def get_user_subscriptions(
        self,
        user_id: int,
        state: Optional[ShipmentState] = None
    ) -> List[tuple[Subscription, Shipment]]:
        """Get all subscriptions for a user with their shipments"""
        # Build aggregation pipeline
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$lookup": {
                    "from": "shipments",
                    "localField": "shipment_id",
                    "foreignField": "_id",
                    "as": "shipment"
                }
            },
            {"$unwind": "$shipment"}
        ]
        
        if state:
            pipeline.append({"$match": {"shipment.state": state.value}})
        
        # PyMongo asyncio: aggregate() is a coroutine that returns an async cursor
        cursor = await self.subscriptions.aggregate(pipeline)
        
        results = []
        async for doc in cursor:
            subscription = Subscription.from_dict(doc)
            shipment = Shipment.from_dict(doc['shipment'])
            results.append((subscription, shipment))
        
        return results
    
    async def get_shipment_subscribers(
        self,
        shipment_id: ObjectId,
        include_muted: bool = False
    ) -> List[Subscription]:
        """Get all subscribers for a shipment"""
        query = {"shipment_id": shipment_id}
        if not include_muted:
            query["muted"] = False
        
        cursor = self.subscriptions.find(query)
        
        subscriptions = []
        async for doc in cursor:
            subscriptions.append(Subscription.from_dict(doc))
        
        return subscriptions
    
    async def delete_subscription(self, user_id: int, shipment_id: ObjectId):
        """Delete a subscription"""
        result = await self.subscriptions.delete_one({
            "user_id": user_id,
            "shipment_id": shipment_id
        })
        logger.info(f"Deleted subscription for user {user_id}")
        return result.deleted_count > 0
    
    async def count_user_active_subscriptions(self, user_id: int) -> int:
        """Count active subscriptions for a user"""
        pipeline = [
            {"$match": {"user_id": user_id}},
            {
                "$lookup": {
                    "from": "shipments",
                    "localField": "shipment_id",
                    "foreignField": "_id",
                    "as": "shipment"
                }
            },
            {"$unwind": "$shipment"},
            {"$match": {"shipment.state": ShipmentState.ACTIVE.value}},
            {"$count": "total"}
        ]
        
        # PyMongo asyncio: aggregate() is a coroutine that returns an async cursor.
        # `$count` returns at most one document.
        cursor = await self.subscriptions.aggregate(pipeline)
        async for doc in cursor:
            return int(doc.get("total", 0))
        return 0
    
    async def toggle_mute(self, user_id: int, shipment_id: ObjectId) -> bool:
        """Toggle mute status for a subscription"""
        subscription = await self.get_subscription(user_id, shipment_id)
        if not subscription:
            return False
        
        new_muted = not subscription.muted
        await self.subscriptions.update_one(
            {"user_id": user_id, "shipment_id": shipment_id},
            {"$set": {"muted": new_muted}}
        )
        
        logger.info(f"Toggled mute for user {user_id}: {new_muted}")
        return new_muted
    
    async def update_subscription_name(
        self,
        user_id: int,
        shipment_id: ObjectId,
        new_name: str
    ) -> bool:
        """Update the item name for a subscription"""
        result = await self.subscriptions.update_one(
            {"user_id": user_id, "shipment_id": shipment_id},
            {"$set": {"item_name": new_name}}
        )
        if result.modified_count > 0:
            logger.info(f"Updated subscription name for user {user_id} to: {new_name}")
            return True
        return False
    
    async def archive_shipment_for_user(self, user_id: int, shipment_id: ObjectId) -> bool:
        """Archive a shipment for a specific user (mark subscription as archived)"""
        # First, check if subscription exists
        subscription = await self.get_subscription(user_id, shipment_id)
        if not subscription:
            return False
        
        # Archive the shipment (this affects all users tracking this shipment)
        await self.shipments.update_one(
            {"_id": shipment_id},
            {
                "$set": {
                    "state": ShipmentState.ARCHIVED.value,
                    "delivered_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        logger.info(f"Archived shipment {shipment_id} by user {user_id}")
        return True
    
    # === Shipment Events Operations (Optional) ===
    
    async def add_shipment_event(self, shipment_id: ObjectId, event: Dict[str, Any]):
        """Add an event to shipment history"""
        event_doc = {
            "shipment_id": shipment_id,
            **event,
            "created_at": datetime.utcnow()
        }
        await self.shipment_events.insert_one(event_doc)
    
    async def get_shipment_events(
        self,
        shipment_id: ObjectId,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent events for a shipment"""
        cursor = self.shipment_events.find(
            {"shipment_id": shipment_id}
        ).sort("timestamp", DESCENDING).limit(limit)
        
        events = []
        async for doc in cursor:
            events.append(doc)
        
        return events


# Global database instance
_db: Optional[Database] = None


async def get_database() -> Database:
    """Get or create the global database instance"""
    global _db
    if _db is None:
        _db = Database()
        await _db.connect()
    return _db
