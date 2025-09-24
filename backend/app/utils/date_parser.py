from datetime import datetime, date, timedelta
import re
from typing import Optional, Tuple
import logging
import calendar

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_user_date(user_input: str, reference_date: date = None) -> str:
    """
    Enhanced date parser with improved flexibility and error handling
    
    Handles formats like:
    - "today", "tomorrow", "yesterday"
    - "16-09", "16/09", "16.09" (adds current year)
    - "16-09-2025", "16/09/2025", "2025-09-16"
    - "16 sep", "sep 16", "16 september", "sep 22nd"
    - "next monday", "last friday", "this weekend"
    - "in 5 days", "5 days from now", "after 3 days"
    - "end of month", "beginning of next month"
    """
    if reference_date is None:
        reference_date = date.today()
    
    user_input = user_input.lower().strip()

    # Handle more relative date variations
    relative_dates = {
        'today': 0, 'now': 0, 'current': 0,
        'tomorrow': 1, 'tmrw': 1, 'next day': 1,
        'yesterday': -1, 'prev day': -1, 'previous day': -1,
        'day after tomorrow': 2, 'overmorrow': 2,
        'day before yesterday': -2
    }
    
    if user_input in relative_dates:
        delta = relative_dates[user_input]
        return (reference_date + timedelta(days=delta)).strftime('%Y-%m-%d')

    # Enhanced "in X days" patterns
    days_patterns = [
        r'(?:in\s+|after\s+)?(\d+)\s+days?\s*(?:from\s+now|later|ahead)?',
        r'(?:after\s+)?(\d+)\s*d(?:ays?)?',  # "after 3d", "5days"
        r'(\d+)\s+days?\s+(?:from\s+)?(?:today|now)'
    ]
    
    for pattern in days_patterns:
        match = re.match(pattern, user_input)
        if match:
            days = int(match.group(1))
            return (reference_date + timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Enhanced weekday handling
    weekdays = {
        'monday': 0, 'mon': 0, 'tuesday': 1, 'tue': 1, 'tues': 1,
        'wednesday': 2, 'wed': 2, 'thursday': 3, 'thu': 3, 'thurs': 3,
        'friday': 4, 'fri': 4, 'saturday': 5, 'sat': 5,
        'sunday': 6, 'sun': 6
    }
    
    weekday_patterns = [
        r'(?:next\s+|coming\s+)?([a-z]+)(?:\s+(?:next\s+)?week)?',
        r'(?:this\s+)?([a-z]+)',
        r'(?:last\s+|previous\s+)([a-z]+)'
    ]
    
    for pattern in weekday_patterns:
        match = re.match(pattern, user_input)
        if match:
            weekday_name = match.group(1)
            if weekday_name in weekdays:
                target_weekday = weekdays[weekday_name]
                current_weekday = reference_date.weekday()
                
                if 'next' in user_input or 'coming' in user_input:
                    days_ahead = (target_weekday - current_weekday + 7) % 7
                    if days_ahead == 0:  # If it's the same day, go to next week
                        days_ahead = 7
                elif 'last' in user_input or 'previous' in user_input:
                    days_behind = (current_weekday - target_weekday) % 7
                    if days_behind == 0:
                        days_behind = 7
                    days_ahead = -days_behind
                else:  # 'this' or no prefix
                    days_ahead = (target_weekday - current_weekday) % 7
                    if days_ahead == 0 and target_weekday != current_weekday:
                        days_ahead = 7  # Next week if not today
                
                return (reference_date + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    # Enhanced month-end/beginning handling
    special_dates = {
        'end of month': 'last_day_current_month',
        'eom': 'last_day_current_month',
        'month end': 'last_day_current_month',
        'beginning of month': 'first_day_current_month',
        'month start': 'first_day_current_month',
        'end of next month': 'last_day_next_month',
        'beginning of next month': 'first_day_next_month',
        'next month start': 'first_day_next_month'
    }
    
    if user_input in special_dates:
        action = special_dates[user_input]
        if action == 'last_day_current_month':
            last_day = calendar.monthrange(reference_date.year, reference_date.month)[1]
            return date(reference_date.year, reference_date.month, last_day).strftime('%Y-%m-%d')
        elif action == 'first_day_current_month':
            return date(reference_date.year, reference_date.month, 1).strftime('%Y-%m-%d')
        elif action == 'last_day_next_month':
            next_month = reference_date.month + 1 if reference_date.month < 12 else 1
            next_year = reference_date.year if reference_date.month < 12 else reference_date.year + 1
            last_day = calendar.monthrange(next_year, next_month)[1]
            return date(next_year, next_month, last_day).strftime('%Y-%m-%d')
        elif action == 'first_day_next_month':
            next_month = reference_date.month + 1 if reference_date.month < 12 else 1
            next_year = reference_date.year if reference_date.month < 12 else reference_date.year + 1
            return date(next_year, next_month, 1).strftime('%Y-%m-%d')

    # Enhanced date format patterns with ordinals
    short_date_patterns = [
        r'(\d{1,2})[-/.](\d{1,2})$',  # DD-MM, DD/MM, DD.MM
        r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})$',  # DD-MM-YY/YYYY
    ]
    
    for pattern in short_date_patterns:
        match = re.match(pattern, user_input)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            
            # Handle year
            if len(match.groups()) == 3:
                year_part = match.group(3)
                if len(year_part) == 2:
                    year = 2000 + int(year_part) if int(year_part) < 50 else 1900 + int(year_part)
                else:
                    year = int(year_part)
            else:
                year = reference_date.year
                try:
                    test_date = date(year, month, day)
                    if test_date < reference_date:
                        year += 1
                except ValueError:
                    continue
            
            try:
                return date(year, month, day).strftime('%Y-%m-%d')
            except ValueError:
                continue

    # ISO format patterns
    iso_patterns = [
        r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})',  # YYYY-MM-DD
        r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})'   # MM-DD-YYYY (US format)
    ]
    
    for i, pattern in enumerate(iso_patterns):
        match = re.match(pattern, user_input)
        if match:
            if i == 0:  # YYYY-MM-DD
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
            else:  # MM-DD-YYYY
                month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            
            try:
                return date(year, month, day).strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    # Enhanced month name handling with ordinals
    month_names = {
        'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
        'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6,
        'jul': 7, 'july': 7, 'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
        'oct': 10, 'october': 10, 'nov': 11, 'november': 11, 'dec': 12, 'december': 12
    }
    
    month_patterns = [
        r'(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]+)(?:\s+(\d{4}))?',  # "22nd sep 2025" or "22 sep"
        r'([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?',  # "sep 22nd 2025" or "sep 22"
        r'([a-z]+)(?:\s+(\d{4}))?'  # "september 2025" or "september" (defaults to 1st)
    ]
    
    for i, pattern in enumerate(month_patterns):
        match = re.match(pattern, user_input)
        if match:
            groups = match.groups()
            
            if i == 0:  # Day first
                day = int(groups[0])
                month_str = groups[1]
                year = int(groups[2]) if groups[2] else reference_date.year
            elif i == 1:  # Month first
                month_str = groups[0]
                day = int(groups[1])
                year = int(groups[2]) if groups[2] else reference_date.year
            else:  # Month only
                month_str = groups[0]
                day = 1  # Default to 1st
                year = int(groups[1]) if groups[1] else reference_date.year
            
            month = month_names.get(month_str)
            if month:
                try:
                    test_date = date(year, month, day)
                    # If the date has passed this year and no year specified, try next year
                    if test_date < reference_date and not any(groups[2:]):
                        year += 1
                    return date(year, month, day).strftime('%Y-%m-%d')
                except ValueError:
                    continue
    
    # Try standard parsing as fallback
    standard_formats = ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y']
    for fmt in standard_formats:
        try:
            parsed_date = datetime.strptime(user_input, fmt).date()
            return parsed_date.strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    # Better logging with suggestions
    logger.warning(f"Could not parse date '{user_input}', defaulting to today. Consider formats like: 'tomorrow', '22/09', 'sep 22nd', 'next friday'")
    return reference_date.strftime('%Y-%m-%d')


def parse_user_date_safe(user_input: str, reference_date: date = None) -> Tuple[str, bool]:
    """
    Parse user date input and return (date_string, is_valid)
    Enhanced with better error reporting
    """
    if not user_input or not user_input.strip():
        return date.today().strftime('%Y-%m-%d'), False
    
    try:
        parsed_date = parse_user_date(user_input.strip(), reference_date)
        
        # Validate parsed date is reasonable
        parsed_date_obj = datetime.strptime(parsed_date, '%Y-%m-%d').date()
        current_date = reference_date or date.today()
        
        # Check if date is too far in the past or future (sanity check)
        days_diff = abs((parsed_date_obj - current_date).days)
        if days_diff > 365:  # More than 1 year
            logger.warning(f"Parsed date {parsed_date} is {days_diff} days from today, might be incorrect")
        
        return parsed_date, True
    except Exception as e:
        logger.error(f"Date parsing failed for '{user_input}': {e}")
        return (reference_date or date.today()).strftime('%Y-%m-%d'), False



