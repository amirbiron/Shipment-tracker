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
            if 'z0' in response:
                track_info = response
            elif 'track_info' in response:
                track_info = response.get('track_info', {})
        
        # Collect events from all sources (z0=origin, z1=destination, z2=combined)
        all_events = []
        
        for field in ['z0', 'z1', 'z2']:
            events_data = track_info.get(field)
            if events_data:
                logger.info(f"{field} type: {type(events_data)}")
                
                # Handle both list and dict formats
                if isinstance(events_data, list):
                    all_events.extend(events_data)
                elif isinstance(events_data, dict):
                    # z0/z1/z2 might be a dict with events inside
                    # Try to extract events from common keys
                    if 'items' in events_data:
                        all_events.extend(events_data.get('items', []))
                    elif 'events' in events_data:
                        all_events.extend(events_data.get('events', []))
                    else:
                        # The dict itself might contain event-like data
                        # Check if it has event fields (a=timestamp, z=status)
                        if 'a' in events_data and 'z' in events_data:
                            all_events.append(events_data)
                        else:
                            # Try to get values if they look like events
                            for key, value in events_data.items():
                                if isinstance(value, dict) and ('a' in value or 'z' in value):
                                    all_events.append(value)
                                elif isinstance(value, list):
                                    all_events.extend(value)
        
        logger.info(f"Total events collected: {len(all_events)}")
        
        if not all_events:
            logger.warning(f"No events found in track_info")
            return None, ""
        
        # Filter out non-dict items
        original_count = len(all_events)
        events = [e for e in all_events if isinstance(e, dict)]
        
        if len(events) != original_count:
            logger.info(f"Filtered to {len(events)} dict events from {original_count}")
        
        if not events:
            logger.warning(f"No valid events after filtering. Sample data: {all_events[:2] if all_events else 'empty'}")
            return None, ""
        
        # Sort by time (newest first)
        events = sorted(events, key=lambda x: x.get('a', '') if isinstance(x, dict) else '', reverse=True)
        latest = events[0]
        
        logger.info(f"Latest event: {latest}")
        
        # Parse event
        status_raw = latest.get('z', '')  # Status description
        location = latest.get('c', '')    # Location
        timestamp_str = latest.get('a', '')  # Timestamp
        
        logger.info(f"Parsing timestamp: '{timestamp_str}'")
        
        # Parse timestamp - try multiple formats
        timestamp = None
        if timestamp_str:
            formats_to_try = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d",
                "%d-%m-%Y %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
            ]
            for fmt in formats_to_try:
                try:
                    timestamp = datetime.strptime(timestamp_str, fmt)
                    logger.info(f"Parsed timestamp with format {fmt}: {timestamp}")
                    break
                except (ValueError, TypeError):
                    continue
        
        if timestamp is None:
            logger.warning(f"Could not parse timestamp: '{timestamp_str}', using None")
            timestamp = None  # Don't use current time as fallback
        
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
        timestamp_str = event.timestamp.isoformat() if event.timestamp else 'none'
        hash_str = f"{event.status_raw}|{timestamp_str}|{event.location or ''}"
        return hashlib.sha1(hash_str.encode()).hexdigest()
    
    # Common 17track carrier codes to names mapping
    CARRIER_CODES = {
        "0": "Auto Detect",
        "3": "China Post",
        "190": "China EMS", 
        "2151": "Cainiao",
        "100002": "Yanwen",
        "100003": "SunYou",
        "7014": "4PX",
        "9061": "Israel Post",
        "5": "Israel Post",
        "21051": "USPS",
        "6": "DHL",
        "2018": "FedEx",
        "21037": "UPS",
    }
    
    def _get_carrier_name(self, carrier_data) -> str:
        """Extract carrier name from carrier data (could be dict, int, or string)"""
        if not carrier_data:
            return ""
        
        if isinstance(carrier_data, dict):
            # Try to get name from dict
            name = carrier_data.get('name', '') or carrier_data.get('_name', '')
            if name:
                return name
            # If no name, try to get code and map it
            code = str(carrier_data.get('code', '') or carrier_data.get('_code', ''))
            if code:
                return self.CARRIER_CODES.get(code, code)
        
        # If it's a number or string, try to map it
        code_str = str(carrier_data)
        return self.CARRIER_CODES.get(code_str, code_str if code_str != "0" else "")
    
    def _extract_events_from_field(self, data, field_name: str) -> List[Dict]:
        """Extract events from a field that could be list, dict, or nested structure"""
        events = []
        
        if isinstance(data, list):
            # Direct list - check each item
            for item in data:
                if isinstance(item, dict):
                    # Check if it's an event (has 'a' for timestamp or 'z' for status)
                    if 'a' in item or 'z' in item:
                        events.append(item)
                    else:
                        # Might be nested, try to extract
                        for val in item.values():
                            if isinstance(val, dict) and ('a' in val or 'z' in val):
                                events.append(val)
                            elif isinstance(val, list):
                                events.extend(self._extract_events_from_field(val, field_name))
        
        elif isinstance(data, dict):
            # Check if the dict itself is an event
            if 'a' in data and 'z' in data:
                events.append(data)
            else:
                # Try to find events in dict values
                for key, val in data.items():
                    if isinstance(val, dict) and ('a' in val or 'z' in val):
                        events.append(val)
                    elif isinstance(val, list):
                        events.extend(self._extract_events_from_field(val, field_name))
                    elif isinstance(val, dict):
                        # Recurse into nested dicts
                        events.extend(self._extract_events_from_field(val, field_name))
        
        return events
    
    def parse_tracking_details_17track(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse complete tracking details from 17TRACK response.
        Returns carriers info and all events from both origin and destination.
        """
        track_info = response.get('track', {})
        
        logger.info(f"track_info keys: {list(track_info.keys())}")
        
        # Get carrier information from multiple possible sources
        w1 = track_info.get('w1')  # Origin carrier
        w2 = track_info.get('w2')  # Destination carrier
        
        # Also check is1/is2 for carrier info
        is1 = track_info.get('is1', {})
        is2 = track_info.get('is2', {})
        
        origin_carrier = self._get_carrier_name(w1) or self._get_carrier_name(is1)
        dest_carrier = self._get_carrier_name(w2) or self._get_carrier_name(is2)
        
        # Build carrier string
        if origin_carrier and dest_carrier and origin_carrier != dest_carrier:
            carriers_str = f"{origin_carrier} ➡️ {dest_carrier}"
        elif origin_carrier:
            carriers_str = origin_carrier
        elif dest_carrier:
            carriers_str = dest_carrier
        else:
            carriers_str = "לא זוהה"
        
        logger.info(f"Carriers: {carriers_str} (w1={w1}, w2={w2}, is1={is1}, is2={is2})")
        
        # Get status code
        status_code = track_info.get('e', 0)  # 10=Transit, 30=Pickup, 40=Delivered
        
        # Collect ALL events from multiple sources
        all_events = []
        
        # Log all available fields to understand structure
        for key in track_info.keys():
            val = track_info.get(key)
            val_type = type(val).__name__
            val_preview = ""
            if isinstance(val, list) and len(val) > 0:
                val_preview = f" (len={len(val)}, first={type(val[0]).__name__})"
            elif isinstance(val, dict):
                val_preview = f" (keys={list(val.keys())[:5]})"
            logger.info(f"  Field '{key}': {val_type}{val_preview}")
        
        # Event fields to check:
        # z0 = latest/combined events
        # z1 = origin country events (e.g., China)
        # z2 = destination country events (e.g., Israel)
        # z9 = additional events
        # ygt1, ygt2, ylt1, ylt2 = more tracking sources
        
        event_fields = ['z0', 'z1', 'z2', 'z9', 'ygt1', 'ygt2', 'ylt1', 'ylt2']
        
        for field in event_fields:
            events_data = track_info.get(field)
            if not events_data:
                continue
            
            events_found = self._extract_events_from_field(events_data, field)
            logger.info(f"Processing {field}: type={type(events_data).__name__}, events_found={len(events_found)}")
            all_events.extend(events_found)
        
        logger.info(f"Total events collected: {len(all_events)}")
        
        # Remove duplicates based on timestamp + status
        seen = set()
        unique_events = []
        for event in all_events:
            key = (event.get('a', ''), event.get('z', ''))
            if key not in seen:
                seen.add(key)
                unique_events.append(event)
        
        # Sort by timestamp (newest first)
        unique_events = sorted(
            unique_events, 
            key=lambda x: x.get('a', '') if isinstance(x, dict) else '', 
            reverse=True
        )
        
        logger.info(f"Unique events after dedup: {len(unique_events)}")
        
        # Format events for display
        formatted_events = []
        for event in unique_events:
            timestamp_str = event.get('a', '')
            status = event.get('z', '')
            location = event.get('c', '')
            
            formatted_events.append({
                'timestamp': timestamp_str,
                'status': status,
                'location': location
            })
        
        return {
            'carriers': carriers_str,
            'origin_carrier': origin_carrier,
            'dest_carrier': dest_carrier,
            'status_code': status_code,
            'events': formatted_events
        }
    
    def parse_all_events_17track(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse all tracking events - wrapper for backward compatibility"""
        details = self.parse_tracking_details_17track(response)
        return details.get('events', [])


# Helper function to get API instance
async def get_tracking_api() -> TrackingAPI:
    """Get tracking API instance (use as context manager)"""
    return TrackingAPI()
