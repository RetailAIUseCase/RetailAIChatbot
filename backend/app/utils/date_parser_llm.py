from datetime import datetime, date, timedelta
import json
import logging
from typing import Tuple, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

class LLMDateParser:
    def __init__(self, openai_client: AsyncOpenAI, model: str = "gpt-4o-mini"):
        self.client = openai_client
        self.model = model
    
    async def parse_date_llm(self, user_input: str, reference_date: date = None) -> str:
        """Parse date using LLM - handles virtually any date format"""
        
        if reference_date is None:
            reference_date = date.today()
        
        current_date_str = reference_date.strftime('%Y-%m-%d')
        current_weekday = reference_date.strftime('%A')
        
        prompt = f"""You are a date parser. Convert the user's date input to YYYY-MM-DD format.

            Current date: {current_date_str} ({current_weekday})

            User input: "{user_input}"

            Rules:
            - Return ONLY the date in YYYY-MM-DD format
            - Handle relative dates (today, tomorrow, yesterday, next week, etc.)
            - Handle specific dates (22/09/2025, sep 22nd, september 22, etc.)
            - Handle weekdays (next monday, this friday, last tuesday)
            - Handle time periods (in 3 days, after 5 days, 2 weeks from now)
            - Handle special cases (end of month, beginning of next month)
            - If no date is mentioned or unclear, default to today's date
            - If year is not specified, use current year unless the date has passed, then use next year

            Examples:
            - "today" → {current_date_str}
            - "tomorrow" → {(reference_date + timedelta(days=1)).strftime('%Y-%m-%d')}
            - "22/09" → 2025-09-22
            - "sep 22nd" → 2025-09-22
            - "next friday" → [calculate next friday from current date]
            - "in 5 days" → {(reference_date + timedelta(days=5)).strftime('%Y-%m-%d')}
            - "end of month" → [last day of current month]

            Response (only the date):"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            
            # Validate the result is a proper date
            try:
                datetime.strptime(result, '%Y-%m-%d')
                logger.info(f"📅 LLM parsed: '{user_input}' → '{result}'")
                return result
            except ValueError:
                logger.warning(f"LLM returned invalid date format: {result}")
                return reference_date.strftime('%Y-%m-%d')
                
        except Exception as e:
            logger.error(f"LLM date parsing failed: {e}")
            return reference_date.strftime('%Y-%m-%d')
    
    async def parse_date_safe(self, user_input: str, reference_date: date = None) -> Tuple[str, bool]:
        """Safe wrapper for LLM date parsing"""
        if not user_input or not user_input.strip():
            return (reference_date or date.today()).strftime('%Y-%m-%d'), False
        
        try:
            result = await self.parse_date_llm(user_input.strip(), reference_date)
            return result, True
        except Exception as e:
            logger.error(f"Date parsing failed: {e}")
            return (reference_date or date.today()).strftime('%Y-%m-%d'), False

