"""
State machine for managing scraping workflow
"""
from enum import Enum
from typing import Optional, Dict, Any, Callable
from loguru import logger
from datetime import datetime


class ScraperState(str, Enum):
    """Possible scraper states"""
    IDLE = "idle"
    INITIALIZING = "initializing"
    LOGGING_IN = "logging_in"
    SEARCHING = "searching"
    AWAITING_COURT_SELECTION = "awaiting_court_selection"
    PROCESSING_RESULTS = "processing_results"
    NAVIGATING_TO_DOCUMENT = "navigating_to_document"
    EXTRACTING_ENTRIES = "extracting_entries"
    AWAITING_TRANSCRIPT_SELECTION = "awaiting_transcript_selection"
    DOWNLOADING = "downloading"
    RETURNING_TO_RESULTS = "returning_to_results"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


class StateMachine:
    """Manages scraper state transitions"""
    
    def __init__(self):
        self.current_state: ScraperState = ScraperState.IDLE
        self.previous_state: Optional[ScraperState] = None
        self.state_history: list = []
        self.context: Dict[str, Any] = {}
        self.on_state_change: Optional[Callable] = None
    
    def set_state_change_callback(self, callback: Callable):
        """
        Set callback to be called on state changes
        
        Args:
            callback: Async function(state, previous_state, message)
        """
        self.on_state_change = callback
    
    async def transition_to(self, new_state: ScraperState, message: str = ""):
        """
        Transition to a new state
        
        Args:
            new_state: Target state
            message: Optional message describing the transition
        """
        self.previous_state = self.current_state
        self.current_state = new_state
        
        # Record in history
        self.state_history.append({
            'state': new_state,
            'previous_state': self.previous_state,
            'message': message,
            'timestamp': datetime.now()
        })
        
        logger.info(f"State transition: {self.previous_state} → {new_state} | {message}")
        
        # Call callback if set
        if self.on_state_change:
            await self.on_state_change(new_state, self.previous_state, message)
    
    def update_context(self, **kwargs):
        """
        Update context with new data
        
        Args:
            **kwargs: Key-value pairs to update in context
        """
        self.context.update(kwargs)
        logger.debug(f"Context updated: {list(kwargs.keys())}")
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """
        Get value from context
        
        Args:
            key: Context key
            default: Default value if key not found
        
        Returns:
            Context value
        """
        return self.context.get(key, default)
    
    def clear_context(self):
        """Clear all context data"""
        self.context = {}
        logger.debug("Context cleared")
    
    def is_in_state(self, *states: ScraperState) -> bool:
        """
        Check if current state is one of the given states
        
        Args:
            *states: Variable number of states to check
        
        Returns:
            True if current state matches any of the given states
        """
        return self.current_state in states
    
    def can_pause(self) -> bool:
        """
        Check if scraper can be paused in current state
        
        Returns:
            True if pause is allowed
        """
        pausable_states = [
            ScraperState.AWAITING_COURT_SELECTION,
            ScraperState.AWAITING_TRANSCRIPT_SELECTION
        ]
        return self.current_state in pausable_states
    
    def get_state_summary(self) -> Dict[str, Any]:
        """
        Get summary of current state
        
        Returns:
            Dictionary with state information
        """
        return {
            'current_state': self.current_state,
            'previous_state': self.previous_state,
            'history_length': len(self.state_history),
            'context_keys': list(self.context.keys())
        }
    
    def get_history(self, limit: int = 10) -> list:
        """
        Get recent state history
        
        Args:
            limit: Maximum number of history items to return
        
        Returns:
            List of recent state transitions
        """
        return self.state_history[-limit:]
    
    def reset(self):
        """Reset state machine to initial state"""
        self.current_state = ScraperState.IDLE
        self.previous_state = None
        self.state_history = []
        self.context = {}
        logger.info("State machine reset")