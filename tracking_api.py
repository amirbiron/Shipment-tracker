"""
17TRACK API integration module
Handles all interactions with the 17TRACK tracking API
"""
import logging
import hashlib
import httpx
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from models import CarrierCandidate, ShipmentEvent, StatusNorm
from config import get_config

logger = logging.getLogger(__name__)


class TrackingAPIError(Exception):
    """Base exception for tracking API errors"""
    pass


class RateLimitError(TrackingAPIError):
    """Rate limit exceeded"""
    pass


class TrackingAPI:
    """17TRACK API client"""
    
    def __init__(self):
        config = get_config()
        self.api_key = config.tracking_api.api_key
        self.base_url = config.tracking_api.base_url
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "17token": self.api_key,
                "Content-Type": "application/json"
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    async def detect_carrier(self, tracking_number: str) -> List[CarrierCandidate]:
        """
        Detect possible carriers for a tracking number
        Returns list of carrier candidates
        """
        # For 17TRACK, we can use the auto-detect feature
        # This is a simplified version - in reality, 17TRACK auto-detects
        
        logger.info(f"Detecting carrier for: {tracking_number}")
        
        # TODO: Implement actual carrier detection API call
        # For now, we'll use a placeholder that returns common carriers
        
        # Regex-based detection (fallback)
        candidates = self._detect_carrier_by_pattern(tracking_number)
        
        if not candidates:
            # If no pattern match, return generic international
            candidates = [
                CarrierCandidate(code="0", name="Auto Detect")
            ]
        
        return candidates
    
    def _detect_carrier_by_pattern(self, tracking_number: str) -> List[CarrierCandidate]:
        """Pattern-based carrier detection (fallback)"""
        tracking_number = tracking_number.upper().strip()
        candidates = []
        
        # China Post (starts with letter, ends with CN)
        if tracking_number.endswith('CN') and len(tracking_number) == 13:
            candidates.append(CarrierCandidate(code="2005", name="China Post"))
            candidates.append(CarrierCandidate(code="2014", name="Cainiao"))
        
        # Israel Post
        elif tracking_number.startswith('IL') or tracking_number.endswith('IL'):
            candidates.append(CarrierCandidate(code="5", name="Israel Post"))
        
        # USPS
        elif tracking_number.startswith('9') and len(tracking_number) in [20, 22]:
            candidates.append(CarrierCandidate(code="21051", name="USPS"))
        
        # DHL
        elif len(tracking_number) == 10 and tracking_number.isdigit():
            candidates.append(CarrierCandidate(code="6", name="DHL"))
        
        # FedEx
        elif len(tracking_number) == 12 and tracking_number.isdigit():
            candidates.append(CarrierCandidate(code="2018", name="FedEx"))
        
        # UPS
        elif tracking_number.startswith('1Z'):
            candidates.append(CarrierCandidate(code="21037", name="UPS"))
        
        return candidates
    
    async def register_tracking(
        self,
        tracking_number: str,
        carrier_code: str
    ) -> bool:
        """
        Register a tracking number with the API
        """
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        url = f"{self.base_url}/register"
        
        payload = [{
            "number": tracking_number,
            "carrier": int(carrier_code) if carrier_code.isdigit() else 0
        }]
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 429:
                raise RateLimitError("API rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            # Check if registration was successful
            if data.get('code') == 0:
                logger.info(f"Registered tracking: {tracking_number}")
                return True
            else:
                logger.warning(f"Registration failed: {data.get('message')}")
                return False
        
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during registration: {e}")
            raise TrackingAPIError(f"Registration failed: {e}")
    
    async def get_tracking_info(
        self,
        tracking_number: str,
        carrier_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get current tracking information for a shipment
        """
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        url = f"{self.base_url}/gettrackinfo"
        
        payload = [{
            "number": tracking_number,
            "carrier": int(carrier_code) if carrier_code.isdigit() else 0
        }]
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 429:
                raise RateLimitError("API rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 0 and data.get('data'):
                accepted = data['data'].get('accepted', [])
                if accepted:
                    return accepted[0]
            
            return None
        
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting tracking info: {e}")
            raise TrackingAPIError(f"Failed to get tracking info: {e}")
    
    async def batch_get_tracking_info(
        self,
        shipments: List[Tuple[str, str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get tracking info for multiple shipments in batch
        shipments: List of (tracking_number, carrier_code) tuples
        Returns: Dict mapping tracking_number to tracking info
        """
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        # 17TRACK allows up to 40 numbers per request
        batch_size = 40
        results = {}
        
        for i in range(0, len(shipments), batch_size):
            batch = shipments[i:i + batch_size]
            
            payload = [
                {
                    "number": tracking_number,
                    "carrier": int(carrier_code) if carrier_code.isdigit() else 0
                }
                for tracking_number, carrier_code in batch
            ]
            
            try:
                url = f"{self.base_url}/gettrackinfo"
                response = await self.client.post(url, json=payload)
                
                if response.status_code == 429:
                    raise RateLimitError("API rate limit exceeded")
                
                response.raise_for_status()
                data = response.json()
                
                if data.get('code') == 0 and data.get('data'):
                    accepted = data['data'].get('accepted', [])
                    for item in accepted:
                        tracking_num = item.get('number')
                        if tracking_num:
                            results[tracking_num] = item
            
            except httpx.HTTPError as e:
                logger.error(f"HTTP error in batch get: {e}")
                # Continue with other batches
        
        return results
    
    def parse_tracking_response(self, response: Dict[str, Any]) -> Tuple[Optional[ShipmentEvent], str]:
        """
        Parse 17TRACK API response to ShipmentEvent
        Returns: (ShipmentEvent, event_hash)
        """
        track_info = response.get('track', {})
        
        # Get latest event
        events = track_info.get('z0', [])  # z0 contains tracking events
        if not events:
            return None, ""
        
        # Sort by time (newest first)
        events = sorted(events, key=lambda x: x.get('z', ''), reverse=True)
        latest = events[0]
        
        # Parse event
        status_raw = latest.get('z', '')  # Status description
        location = latest.get('c', '')    # Location
        timestamp_str = latest.get('a', '')  # Timestamp
        
        # Parse timestamp
        try:
            # 17TRACK format: "2025-01-17 10:00:00"
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            timestamp = datetime.utcnow()
        
        # Normalize status
        status_norm = self._normalize_status(status_raw, track_info)
        
        # Create event
        event = ShipmentEvent(
            status_raw=status_raw,
            status_norm=status_norm,
            timestamp=timestamp,
            location=location,
            raw=latest
        )
        
        # Calculate hash for change detection
        event_hash = self._calculate_event_hash(event)
        
        return event, event_hash
    
    def _normalize_status(self, status_raw: str, track_info: Dict) -> StatusNorm:
        """Normalize status text to StatusNorm enum"""
        status_lower = status_raw.lower()
        
        # Check 17TRACK status codes
        status_code = track_info.get('b', 0)  # b is the status code
        
        # Status codes from 17TRACK
        if status_code == 40:  # Delivered
            return StatusNorm.DELIVERED
        elif status_code == 30:  # Pickup
            return StatusNorm.OUT_FOR_DELIVERY
        elif status_code == 20:  # In transit
            return StatusNorm.IN_TRANSIT
        elif status_code == 10:  # Info received
            return StatusNorm.INFO_RECEIVED
        elif status_code == 50:  # Exception
            return StatusNorm.EXCEPTION
        elif status_code == 0:  # Not found
            return StatusNorm.UNKNOWN
        
        # Keyword-based fallback
        if any(word in status_lower for word in ['delivered', 'נמסר']):
            return StatusNorm.DELIVERED
        elif any(word in status_lower for word in ['out for delivery', 'יצא לחלוקה']):
            return StatusNorm.OUT_FOR_DELIVERY
        elif any(word in status_lower for word in ['customs', 'מכס']):
            return StatusNorm.CUSTOMS
        elif any(word in status_lower for word in ['arrived', 'הגיע']):
            if 'destination' in status_lower or 'יעד' in status_lower:
                return StatusNorm.ARRIVED_DESTINATION
            else:
                return StatusNorm.ARRIVED_SORTING_CENTER
        elif any(word in status_lower for word in ['in transit', 'בדרך']):
            return StatusNorm.IN_TRANSIT
        elif any(word in status_lower for word in ['exception', 'חריגה', 'problem', 'בעיה']):
            return StatusNorm.EXCEPTION
        elif any(word in status_lower for word in ['expired', 'פג']):
            return StatusNorm.EXPIRED
        
        return StatusNorm.IN_TRANSIT  # Default
    
    def _calculate_event_hash(self, event: ShipmentEvent) -> str:
        """Calculate SHA1 hash of event for change detection"""
        hash_str = f"{event.status_raw}|{event.timestamp.isoformat()}|{event.location or ''}"
        return hashlib.sha1(hash_str.encode()).hexdigest()


# Helper function to get API instance
async def get_tracking_api() -> TrackingAPI:
    """Get tracking API instance (use as context manager)"""
    return TrackingAPI()
