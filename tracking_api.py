"""
Tracking API integration module
Supports both 17TRACK and TrackingMore APIs
Handles carrier detection, tracking info retrieval, and status parsing
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
    """Multi-provider Tracking API client (17TRACK / TrackingMore)"""
    
    def __init__(self):
        config = get_config()
        self.provider = config.tracking_api.provider
        self.api_key = config.tracking_api.api_key
        self.base_url = config.tracking_api.base_url
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        headers = self._get_headers()
        
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers
        )
        return self
    
    def _get_headers(self) -> Dict[str, str]:
        """Get appropriate headers based on provider"""
        if self.provider == 'trackingmore':
            return {
                "Tracking-Api-Key": self.api_key,
                "Content-Type": "application/json"
            }
        else:  # 17track
            return {
                "17token": self.api_key,
                "Content-Type": "application/json"
            }
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.client:
            await self.client.aclose()
    
    async def detect_carrier(self, tracking_number: str) -> List[CarrierCandidate]:
        """
        Detect possible carriers for a tracking number
        Returns list of carrier candidates
        """
        logger.info(f"Detecting carrier for: {tracking_number} (provider: {self.provider})")
        
        if self.provider == 'trackingmore':
            return await self._detect_carrier_trackingmore(tracking_number)
        else:
            return await self._detect_carrier_17track(tracking_number)
    
    async def _detect_carrier_trackingmore(self, tracking_number: str) -> List[CarrierCandidate]:
        """TrackingMore carrier detection"""
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        try:
            # TrackingMore detect API
            url = f"{self.base_url}/carriers/detect"
            payload = {"tracking_number": tracking_number}
            
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 200 and data.get('data'):
                carriers_data = data['data']
                candidates = []
                
                for carrier in carriers_data[:5]:  # Max 5
                    candidates.append(CarrierCandidate(
                        code=carrier.get('code', ''),
                        name=carrier.get('name', '')
                    ))
                
                return candidates if candidates else self._detect_carrier_by_pattern(tracking_number)
            
            # Fallback to pattern detection
            return self._detect_carrier_by_pattern(tracking_number)
        
        except httpx.HTTPError as e:
            logger.warning(f"TrackingMore detect error: {e}, using pattern fallback")
            return self._detect_carrier_by_pattern(tracking_number)
    
    async def _detect_carrier_17track(self, tracking_number: str) -> List[CarrierCandidate]:
        """17TRACK carrier detection (pattern-based fallback)"""
        # 17TRACK auto-detects, so we use pattern matching
        candidates = self._detect_carrier_by_pattern(tracking_number)
        
        if not candidates:
            # If no pattern match, return generic auto-detect
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
        """Register a tracking number with the API"""
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        if self.provider == 'trackingmore':
            return await self._register_trackingmore(tracking_number, carrier_code)
        else:
            return await self._register_17track(tracking_number, carrier_code)
    
    async def _register_trackingmore(self, tracking_number: str, carrier_code: str) -> bool:
        """TrackingMore registration"""
        url = f"{self.base_url}/trackings/create"
        
        payload = {
            "tracking_number": tracking_number,
            "carrier_code": carrier_code
        }
        
        try:
            response = await self.client.post(url, json=payload)
            
            if response.status_code == 429:
                raise RateLimitError("API rate limit exceeded")
            
            data = response.json()
            
            # TrackingMore returns 200/4031 for already exists
            if data.get('code') in [200, 4031]:
                logger.info(f"Registered tracking: {tracking_number}")
                return True
            else:
                logger.warning(f"Registration response: {data}")
                return True  # Still proceed
        
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during registration: {e}")
            return True  # Proceed anyway, might work with get
    
    async def _register_17track(self, tracking_number: str, carrier_code: str) -> bool:
        """17TRACK registration"""
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
        """Get current tracking information for a shipment"""
        if not self.client:
            raise TrackingAPIError("API client not initialized")
        
        if self.provider == 'trackingmore':
            return await self._get_info_trackingmore(tracking_number, carrier_code)
        else:
            return await self._get_info_17track(tracking_number, carrier_code)
    
    async def _get_info_trackingmore(
        self,
        tracking_number: str,
        carrier_code: str
    ) -> Optional[Dict[str, Any]]:
        """TrackingMore get tracking info"""
        url = f"{self.base_url}/trackings/get"
        
        params = {
            "tracking_numbers": tracking_number,
            "carrier_code": carrier_code
        }
        
        try:
            response = await self.client.get(url, params=params)
            
            if response.status_code == 429:
                raise RateLimitError("API rate limit exceeded")
            
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 200 and data.get('data'):
                items = data['data']
                if items and len(items) > 0:
                    return items[0]
            
            return None
        
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting tracking info: {e}")
            raise TrackingAPIError(f"Failed to get tracking info: {e}")
    
    async def _get_info_17track(
        self,
        tracking_number: str,
        carrier_code: str
    ) -> Optional[Dict[str, Any]]:
        """17TRACK get tracking info"""
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
            
            logger.info(f"17track API response for {tracking_number}: code={data.get('code')}")
            
            if data.get('code') == 0 and data.get('data'):
                accepted = data['data'].get('accepted', [])
                rejected = data['data'].get('rejected', [])
                
                if rejected:
                    logger.warning(f"17track rejected {tracking_number}: {rejected}")
                
                if accepted:
                    result = accepted[0]
                    logger.info(f"17track accepted response keys: {result.keys() if isinstance(result, dict) else type(result)}")
                    return result
            
            logger.warning(f"17track no data for {tracking_number}, full response: {data}")
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
        Parse API response to ShipmentEvent
        Returns: (ShipmentEvent, event_hash)
        """
        if self.provider == 'trackingmore':
            return self._parse_trackingmore(response)
        else:
            return self._parse_17track(response)
    
    def _parse_trackingmore(self, response: Dict[str, Any]) -> Tuple[Optional[ShipmentEvent], str]:
        """Parse TrackingMore response"""
        # Get origin_info (tracking events)
        events = response.get('origin_info', {}).get('trackinfo', [])
        
        if not events:
            return None, ""
        
        # Latest event (first in list)
        latest = events[0] if isinstance(events, list) else events
        
        # Parse event
        status_raw = latest.get('StatusDescription', '') or latest.get('checkpoint_status', '')
        location = latest.get('checkpoint_delivery_location', '') or latest.get('Details', '')
        timestamp_str = latest.get('checkpoint_date', '') or latest.get('Date', '')
        
        # Parse timestamp
        try:
            # TrackingMore format: "2025-01-17 10:00:00" or ISO
            if 'T' in timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            timestamp = datetime.utcnow()
        
        # Normalize status
        status_code = response.get('status', '')
        status_norm = self._normalize_status_trackingmore(status_raw, status_code)
        
        # Create event
        event = ShipmentEvent(
            status_raw=status_raw,
            status_norm=status_norm,
            timestamp=timestamp,
            location=location,
            raw=latest
        )
        
        # Calculate hash
        event_hash = self._calculate_event_hash(event)
        
        return event, event_hash
    
    def _parse_17track(self, response: Dict[str, Any]) -> Tuple[Optional[ShipmentEvent], str]:
        """Parse 17TRACK response"""
        logger.info(f"Parsing 17track response, keys: {response.keys() if isinstance(response, dict) else type(response)}")
        
        track_info = response.get('track', {})
        
        # Log track_info structure
        if track_info:
            logger.info(f"track_info keys: {track_info.keys() if isinstance(track_info, dict) else type(track_info)}")
        else:
            logger.warning(f"No 'track' in response. Full response: {response}")
            # Try alternative structures
            # Sometimes the track info might be directly in response
            if 'z0' in response:
                track_info = response
            elif 'track_info' in response:
                track_info = response.get('track_info', {})
        
        # Get latest event - try multiple possible field names
        events = track_info.get('z0', []) or track_info.get('z1', []) or track_info.get('z2', [])
        
        logger.info(f"Events found: {len(events) if events else 0}, type: {type(events)}")
        
        if not events:
            # Log what we have
            logger.warning(f"No events in track_info. track_info: {track_info}")
            return None, ""
        
        # Filter out non-dict items (sometimes API returns strings)
        original_count = len(events)
        events = [e for e in events if isinstance(e, dict)]
        
        if len(events) != original_count:
            logger.warning(f"Filtered out {original_count - len(events)} non-dict events")
        
        if not events:
            logger.warning(f"No dict events after filtering")
            return None, ""
        
        # Sort by time (newest first)
        events = sorted(events, key=lambda x: x.get('a', '') if isinstance(x, dict) else '', reverse=True)
        latest = events[0]
        
        logger.info(f"Latest event: {latest}")
        
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
        
        # Calculate hash
        event_hash = self._calculate_event_hash(event)
        
        return event, event_hash
    
    def _normalize_status_trackingmore(self, status_raw: str, status_code: str) -> StatusNorm:
        """Normalize TrackingMore status"""
        status_lower = status_raw.lower()
        
        # TrackingMore status codes
        status_map = {
            'delivered': StatusNorm.DELIVERED,
            'transit': StatusNorm.IN_TRANSIT,
            'pickup': StatusNorm.OUT_FOR_DELIVERY,
            'undelivered': StatusNorm.EXCEPTION,
            'expired': StatusNorm.EXPIRED,
            'notfound': StatusNorm.UNKNOWN,
            'pending': StatusNorm.INFO_RECEIVED
        }
        
        # Check status code first
        if status_code in status_map:
            return status_map[status_code]
        
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
        elif any(word in status_lower for word in ['in transit', 'בדרך', 'transit']):
            return StatusNorm.IN_TRANSIT
        elif any(word in status_lower for word in ['exception', 'חריגה', 'problem', 'בעיה', 'failed']):
            return StatusNorm.EXCEPTION
        
        return StatusNorm.IN_TRANSIT  # Default
    
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
