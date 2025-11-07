"""
AI-powered chart suggestions with visual previews and PDF export
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime
from openai import AsyncOpenAI
from app.config.settings import settings
import base64
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from PIL import Image
import kaleido
import uuid

logger = logging.getLogger(__name__)
logging.getLogger("kaleido").setLevel(logging.ERROR)
logging.getLogger("choreographer").setLevel(logging.ERROR)

class ChartService:
    """AI-powered chart generation with suggestions and PDF export"""
    
    CHART_TYPES = {
        'line': {
            'name': 'Line Chart',
            'description': 'Shows trends and changes over time',
            'icon': '📈',
            'best_for': 'Time series, trends, projections'
        },
        'bar': {
            'name': 'Bar Chart',
            'description': 'Compares discrete categories',
            'icon': '📊',
            'best_for': 'Category comparisons, rankings'
        },
        'stacked_bar': {
            'name': 'Stacked Bar',
            'description': 'Shows part-to-whole relationships',
            'icon': '📊',
            'best_for': 'Composition across categories'
        },
        'area': {
            'name': 'Area Chart',
            'description': 'Shows cumulative totals over time',
            'icon': '📈',
            'best_for': 'Volume trends, cumulative data'
        },
        'pie': {
            'name': 'Pie Chart',
            'description': 'Shows composition and percentages',
            'icon': '🥧',
            'best_for': 'Percentage breakdown (5-7 categories)'
        },
        'grouped_bar': {
            'name': 'Grouped Bar',
            'description': 'Side-by-side category comparisons',
            'icon': '📊',
            'best_for': 'Multi-series comparison'
        },
        'scatter': {
            'name': 'Scatter Plot',
            'description': 'Shows relationships between variables',
            'icon': '⚫',
            'best_for': 'Correlation, clustering'
        }
    }
    
    NAGARRO_COLORS = ['#47D7AC', '#18483A', '#6EDFC2', '#2A6B5B', '#8FE8D0']
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.llm_model = settings.NLP_LLM_MODEL
    
    async def suggest_chart_options(
        self,
        query: str,
        data: List[Dict],
        intent: str = "visualization"
    ) -> Dict[str, Any]:
        """
        Use AI to suggest 3 best chart types with thumbnail previews
        """
        
        try:
            # Analyze data characteristics
            data_analysis = self._analyze_data(data)
            
            # AI prompt for intelligent suggestions
            suggestion_prompt = f"""
                        You are a data visualization expert. Suggest 2-3 BEST chart types for this data.

                        **User Query:** {query}
                        **Intent:** {intent}

                        **Data Analysis:**
                        - Rows: {data_analysis['row_count']}
                        - Columns: {', '.join(data_analysis['columns'])}
                        - Temporal: {', '.join(data_analysis['temporal_columns']) or 'None'}
                        - NUMERIC columns (for Y-axis): {', '.join(data_analysis['numeric_columns'])}
                        - CATEGORICAL columns (for labels/categories): {', '.join(data_analysis['categorical_columns'])}
                        - Time series: {data_analysis['is_time_series']}
                        - Date range: {data_analysis.get('date_range', 'N/A')}

                        **Sample Data (first 3 rows):**
                        {json.dumps(data[:3], indent=2, default=str)}

                        **Available Chart Types:**
                        {json.dumps({k: v['description'] for k, v in self.CHART_TYPES.items()}, indent=2)}
                        
                        **IMPORTANT RULES FOR CONFIG:**
                            1. For PIE charts: x must be CATEGORICAL, y MUST be NUMERIC (e.g., total_invoice_amount, quantity, value)
                            2. For BAR charts: x can be categorical or first column, y MUST be NUMERIC
                            3. For LINE charts: x can be temporal/date, y MUST be NUMERIC
                            4. For SCATTER: x MUST be NUMERIC, y MUST be NUMERIC
                            5. NEVER use currency/codes/text columns for y-axis values
                            6. ALWAYS pick the MOST RELEVANT numeric column for values (not just any numeric)
                        
                        Suggest upto 3 chart types in preference order.

                        Respond in JSON:
                        {{
                        "suggestions": [
                            {{
                            "chart_type": "line",
                            "confidence": 95,
                            "reasoning": "Time series data is best visualized with line charts to show trends",
                            "config": {{
                                "x": "date_column",
                                "y": ["value_column"],
                                "group_by": null
                            }},
                            "title": "Suggested chart title"
                            }},
                            // ... 2 more suggestions
                        ],
                        "data_insights": "Brief insight about data patterns",
                        "suggested_questions": ["Follow-up question 1", "Follow-up question 2"]
                        }}
                        **CRITICAL VALIDATION:**
                            - x column MUST exist in provided columns
                            - y columns MUST be from NUMERIC columns list
                            - For pie: x MUST be categorical, y MUST be numeric
                            - DO NOT make up column names
                        """
            
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "You are a data visualization expert."},
                    {"role": "user", "content": suggestion_prompt}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            
            ai_suggestions = json.loads(response.choices[0].message.content)

            # **VALIDATE and FIX LLM suggestions before using**
            # valid_suggestions = []
            # for suggestion in ai_suggestions.get('suggestions', []):
            #     chart_type = suggestion['chart_type']
            #     config = suggestion.get('config', {})
                
            #     # Validate x column
            #     x_col = config.get('x')
            #     if not x_col or x_col not in data_analysis['columns']:
            #         # Auto-fix: use first categorical for pie/bar, first column for others
            #         if chart_type in ['pie', 'bar', 'grouped_bar', 'stacked_bar']:
            #             x_col = data_analysis['categorical_columns'][0] if data_analysis['categorical_columns'] else data_analysis['columns'][0]
            #         else:
            #             x_col = data_analysis['columns'][0]
            #         config['x'] = x_col
                
            #     # Validate y columns
            #     y_cols = config.get('y', [])
            #     if isinstance(y_cols, str):
            #         y_cols = [y_cols]
                
            #     # **CRITICAL: Ensure y columns are numeric**
            #     valid_y_cols = [col for col in y_cols if col in data_analysis['numeric_columns']]
                
            #     if not valid_y_cols:
            #         # Auto-fix: use first numeric column
            #         if data_analysis['numeric_columns']:
            #             valid_y_cols = [data_analysis['numeric_columns'][0]]
            #         else:
            #             # No numeric columns found - remove this suggestion
            #             ai_suggestions['suggestions'].remove(suggestion)
            #             continue
                
            #     config['y'] = valid_y_cols
            #     # logger.info(f"✅ Validated suggestion: chart={chart_type}, x={config['x']}, y={config['y']}")
            #     # Add back to valid suggestions
            #     suggestion['config'] = config
            #     valid_suggestions.append(suggestion)
            
            # # Use only validated suggestions
            # ai_suggestions['suggestions'] = valid_suggestions
            
            # if not valid_suggestions:
            #     logger.warning("No valid suggestions after validation, using fallback")
            #     return await self._fallback_suggestions(query, data)
            
            # Generate thumbnail previews for each suggestion
            thumbnails = await self._generate_thumbnails(
                data[:20],  # Use first 20 rows
                ai_suggestions['suggestions'],
                data_analysis
            )
            
            # Add chart type metadata
            for suggestion in ai_suggestions['suggestions']:
                chart_type = suggestion['chart_type']
                if chart_type in self.CHART_TYPES:
                    suggestion['metadata'] = self.CHART_TYPES[chart_type]
                    suggestion['thumbnail'] = thumbnails.get(chart_type)
            
            return {
                'success': True,
                'suggestions': ai_suggestions['suggestions'],
                'data_insights': ai_suggestions.get('data_insights', ''),
                'suggested_questions': ai_suggestions.get('suggested_questions', []),
                'data_summary': data_analysis
            }
            
        except Exception as e:
            logger.error(f"AI suggestion error: {e}")
            return await self._fallback_suggestions(query, data)
    def _categorize_columns(self, df: pd.DataFrame) -> tuple[List[str], List[str], List[str]]:
        """
        Column categorization for ALL query types.
        Returns: (temporal_cols, numeric_cols, categorical_cols)
        
        Handles:
        - Numeric strings from database ("1000" → 1000)
        - Date columns (automatic detection)
        - IDs that look numeric but aren't (SKU001, IN01 → categorical)
        - Mixed data types
        """
        
        temporal_cols = []
        numeric_cols = []
        categorical_cols = []
        
        for col in df.columns:
            # ===== STEP 1: Check if it's a date column =====
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                temporal_cols.append(col)
                continue
            
            # Check column name hints
            if any(word in col.lower() for word in ['date', 'time', 'day', 'month', 'year', 'week']):
                try:
                    converted = pd.to_datetime(df[col], errors='coerce')
                    if converted.notna().sum() / len(df) >= 0.8:
                        temporal_cols.append(col)
                        df[col] = converted
                        continue
                except:
                    pass
            
            # ===== STEP 2: Try to convert to numeric =====
            try:
                converted = pd.to_numeric(df[col], errors='coerce')
                success_count = converted.notna().sum()
                total_count = len(df)
                
                # Only mark as numeric if 80%+ values converted successfully
                if success_count / total_count >= 0.8:
                    numeric_cols.append(col)
                    df[col] = converted  # Keep converted values
                    continue
            except (ValueError, TypeError):
                pass
            
            # ===== STEP 3: If not numeric and not temporal → CATEGORICAL =====
            categorical_cols.append(col)
        
        # logger.info(f"🔍 Column Classification: Temporal={temporal_cols}, Numeric={numeric_cols}, Categorical={categorical_cols}")
        return temporal_cols, numeric_cols, categorical_cols

    def _analyze_data(self, data: List[Dict]) -> Dict[str, Any]:
        """Analyze data characteristics"""
        
        if not data:
            return {'row_count': 0, 'columns': []}
        
        df = pd.DataFrame(data)
        # for col in df.columns:
        #     try:
        #         # Try to convert to numeric
        #         df[col] = pd.to_numeric(df[col], errors='coerce')
        #     except:
        #         pass
        # temporal_cols = []
        # numeric_cols = []
        # categorical_cols = []
        
        # for col in df.columns:
        #     if pd.api.types.is_datetime64_any_dtype(df[col]) or \
        #        any(word in col.lower() for word in ['date', 'time', 'day', 'month', 'year', 'week']):
        #         temporal_cols.append(col)
        #     elif pd.api.types.is_numeric_dtype(df[col]):
        #         numeric_cols.append(col)
        #     else:
        #         categorical_cols.append(col)
        temporal_cols, numeric_cols, categorical_cols = self._categorize_columns(df)
        is_time_series = len(temporal_cols) > 0
        
        date_range = None
        if temporal_cols:
            try:
                date_col = temporal_cols[0]
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                date_range = f"{df[date_col].min()} to {df[date_col].max()}"
            except:
                pass
        # print(temporal_cols, numeric_cols, categorical_cols)
        return {
            'row_count': len(df),
            'columns': list(df.columns),
            'temporal_columns': temporal_cols,
            'numeric_columns': numeric_cols,
            'categorical_columns': categorical_cols,
            'is_time_series': is_time_series,
            'date_range': date_range,
            'has_multiple_metrics': len(numeric_cols) > 1
        }
    
    async def _get_columns_via_llm(
        self,
        df: pd.DataFrame,
        chart_type: str,
        user_query: str
    ) -> tuple[str, List[str]]:
        """
        Smart LLM-based column detection when manual detection fails.
        Only called as FALLBACK - not for every chart.
        """
        
        try:
            # Prepare data info for LLM
            column_info = []
            for col in df.columns:
                dtype = df[col].dtype.name
                sample = str(df[col].iloc[0]) if len(df) > 0 else "N/A"
                is_numeric = pd.api.types.is_numeric_dtype(df[col])
                is_datetime = pd.api.types.is_datetime64_any_dtype(df[col])
                
                column_info.append({
                    'name': col,
                    'type': dtype,
                    'sample_value': sample,
                    'is_numeric': is_numeric,
                    'is_datetime': is_datetime,
                    'unique_count': len(df[col].unique())
                })
            
            # Create LLM prompt
            llm_prompt = f"""You are a data visualization expert. Given the user's query and available columns, 
                    determine which columns to use for a {chart_type} chart.

                    User Query: "{user_query}"

                    Available Columns:
                    {json.dumps(column_info, indent=2)}

                    For a {chart_type} chart, provide:
                    1. x_column: The column to use for X-axis
                    2. y_columns: List of columns for Y-axis values

                    Chart Type Guidelines:
                    - pie: x=categorical (names), y=single numeric column (values)
                    - line/area: x=temporal or numeric (time), y=numeric columns
                    - bar: x=categorical or first column, y=numeric values
                    - scatter: x=numeric, y=numeric
                    - grouped_bar: x=categorical, y=multiple numeric

                    IMPORTANT: Return ONLY valid column names that exist in the provided list.

                    Respond with ONLY valid JSON (no markdown, no extra text):
                    {{
                        "x_column": "actual_column_name",
                        "y_columns": ["column1", "column2"],
                        "reasoning": "brief explanation"
                    }}"""
            
            logger.info(f"🧠 Calling LLM for column detection (chart: {chart_type})")
            
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": llm_prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=150
            )
            
            result = json.loads(response.choices[0].message.content)
            x_col = result.get('x_column')
            y_cols = result.get('y_columns', [])
            
            # Validate LLM response
            if x_col and x_col in df.columns and y_cols and all(col in df.columns for col in y_cols):
                logger.info(f"✅ LLM detected: x={x_col}, y={y_cols}")
                return x_col, y_cols
            else:
                logger.warning(f"⚠️ LLM returned invalid columns: {result}")
                return None, None
                
        except Exception as e:
            logger.error(f"LLM column detection failed: {e}")
            return None, None

    def _get_optimal_columns(
        self, 
        df: pd.DataFrame, 
        chart_type: str, 
        config: Dict,
    ) -> tuple[str, List[str]]:
        """
        Intelligently select x and y columns
        for ANY chart type based on data characteristics.
        
        Returns: (x_column, y_columns_list)
        """
        
        if df.empty:
            raise ValueError("DataFrame is empty")
        # for col in df.columns:
        #     try:
        #         df[col] = pd.to_numeric(df[col], errors='coerce')
        #     except:
        #         pass
        # # Categorize columns
        # temporal_cols = [col for col in df.columns if pd.api.types.is_datetime64_any_dtype(df[col]) or 
        #                 any(word in col.lower() for word in ['date', 'time', 'day', 'month', 'year', 'week'])]
        # numeric_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
        # categorical_cols = [col for col in df.columns if not pd.api.types.is_numeric_dtype(df[col])]
        temporal_cols, numeric_cols, categorical_cols = self._categorize_columns(df)
        # Remove x_col from numeric_cols to avoid duplicates
        config_x = config.get('x')
        config_y = config.get('y', [])
        
        # Ensure config_y is a list
        if isinstance(config_y, str):
            config_y = [config_y]
        # logger.info(f"Column Detection: Temporal={temporal_cols}, Numeric={numeric_cols}, Categorical={categorical_cols}")
        # ============================================================================
        # CHART-TYPE SPECIFIC LOGIC 
        # ============================================================================
        try: 
            x_col, y_cols = None, None
            if chart_type == 'pie':
                # PIE CHART: Needs categorical names + numeric values
                # x = categorical, y = single numeric value
                
                # Get x from config or use first categorical column
                if config_x and config_x in df.columns:
                    x_col = config_x
                elif categorical_cols:
                    x_col = categorical_cols[0]
                else:
                    # Fallback: use first column as category
                    non_numeric = [col for col in df.columns if col not in numeric_cols]
                    if non_numeric:
                        x_col = non_numeric[0]
                    else:
                        x_col = df.columns[0]
                
                # Get y from config or use first numeric column
                if config_y:
                    y_cols = [col for col in config_y if col in df.columns and col in numeric_cols]
                
                # If no y_cols from config, get from numeric_cols
                if not y_cols and numeric_cols:
                    # Exclude x_col if it's somehow in numeric_cols
                    y_cols = [col for col in numeric_cols if col != x_col]
                
                # If still no y_cols, take first numeric column
                if not y_cols:
                    if numeric_cols:
                        y_cols = [numeric_cols[0]]
                    else:
                        y_cols = [df.columns[-1]]
            
            elif chart_type in ['line', 'area']:
                # TIME SERIES: Prefer temporal x-axis
                # x = time column, y = numeric values
                
                # Get x from config or use first temporal/numeric column
                if config_x and config_x in df.columns:
                    x_col = config_x
                elif temporal_cols:
                    x_col = temporal_cols[0]
                elif numeric_cols:
                    x_col = numeric_cols[0]
                else:
                    x_col = df.columns[0]
                
                # Get y columns (all numeric except x_col)
                if config_y:
                    y_cols = [col for col in config_y if col in df.columns and col in numeric_cols and col != x_col]
                else:
                    y_cols = [col for col in numeric_cols if col != x_col]
                
                # Fallback if no numeric columns
                if not y_cols:
                    if len(df.columns) > 1:
                        y_cols = [col for col in df.columns if col != x_col][0:1]
                    else:
                        y_cols = [df.columns[0]]
                
            elif chart_type in ['bar', 'grouped_bar', 'stacked_bar']:
                # BAR CHART: Categorical x-axis preferred
                # x = categorical/first column, y = numeric values
                
                # Get x from config or use first categorical, then fallback
                if config_x and config_x in df.columns:
                    x_col = config_x
                elif categorical_cols:
                    x_col = categorical_cols[0]
                else:
                    # Fallback: use first column
                    x_col = df.columns[0]
                
                # Get y columns (all numeric except x_col)
                if config_y:
                    y_cols = [col for col in config_y if col in df.columns and col in numeric_cols]
                else:
                    y_cols = [col for col in numeric_cols if col != x_col]
                
                # Fallback if no numeric columns
                if not y_cols:
                    if len(df.columns) > 1:
                        available = [col for col in df.columns if col != x_col]
                        y_cols = available[0:1] if available else [df.columns[0]]
                    else:
                        y_cols = [df.columns[0]]
            
            elif chart_type == 'scatter':
                # SCATTER: Two numeric columns
                # x = first numeric, y = second numeric
                
                if config_x and config_x in numeric_cols:
                    x_col = config_x
                elif temporal_cols:
                    x_col = temporal_cols[0]
                elif numeric_cols:
                    x_col = numeric_cols[0]
                else:
                    x_col = df.columns[0]
                
                if config_y:
                    y_cols = [col for col in config_y if col in numeric_cols]
                else:
                    y_cols = [col for col in numeric_cols if col != x_col]
                
                if not y_cols:
                    if len(numeric_cols) > 1:
                        y_cols = [numeric_cols[1]]
                    elif len(df.columns) > 1:
                        y_cols = [df.columns[1]]
                    else:
                        raise ValueError("Scatter chart needs at least 2 columns")
                
            
            else:
                # DEFAULT: Use first column as x, numeric as y
                x_col = config_x if config_x and config_x in df.columns else df.columns[0]
                y_cols = config_y if config_y else [df.columns[1] if len(df.columns) > 1 else df.columns[0]]
                
            if x_col and y_cols:
                # logger.info(f"⚡ Manual detection succeeded: x={x_col}, y={y_cols}")
                return x_col, y_cols
            
            # Fallback
            logger.warning(f"⚠️ Column detection incomplete, using defaults")
            return df.columns[0], [df.columns[1] if len(df.columns) > 1 else df.columns[0]]
        
            
        except Exception as e:
            logger.error(f"Column detection error: {e}")
            raise ValueError(f"Could not determine chart columns: {e}")

    async def _generate_thumbnails(
        self,
        sample_data: List[Dict],
        suggestions: List[Dict],
        data_analysis: Dict,
    ) -> Dict[str, str]:
        """Generate base64 thumbnail images for each suggested chart"""
        
        thumbnails = {}
        
        try:
            for suggestion in suggestions:
                chart_type = suggestion['chart_type']
                config = suggestion.get('config', {})
                
                # Create mini chart
                fig = self._create_mini_chart(
                    sample_data,
                    chart_type,
                    config
                )
                
                # Convert to PNG bytes
                img_bytes = fig.to_image(format="png", width=280, height=180, scale=2)
                img_base64 = base64.b64encode(img_bytes).decode()
                
                thumbnails[chart_type] = f"data:image/png;base64,{img_base64}"
                
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")
            # Use SVG placeholders
            thumbnails = self._get_svg_placeholders(suggestions)
        
        return thumbnails
    
    def _create_mini_chart(self, data: List[Dict], chart_type: str, config: Dict) -> go.Figure:
        """Create small preview chart"""
        
        df = pd.DataFrame(data)
        if df.empty:
            return go.Figure()
        try:
            try:
                x_col, y_cols = self._get_optimal_columns(df, chart_type, config)
            except ValueError as e:
                logger.warning(f"_get_optimal_columns failed for {chart_type}: {e}, using defaults")
                # Fallback to simple column selection
                x_col = df.columns[0]
                y_cols = [df.columns[-1]] if len(df.columns) > 1 else [df.columns[0]]
        
            y_col = y_cols[0] if y_cols else df.columns[0]
        
            if chart_type == 'line':
                fig = px.line(df, x=x_col, y=y_col, markers=True)
            elif chart_type in ['bar', 'grouped_bar']:
                fig = px.bar(df, x=x_col, y=y_col)
            elif chart_type == 'pie':
                fig = px.pie(df, names=x_col, values=y_col)
            elif chart_type == 'area':
                fig = px.area(df, x=x_col, y=y_col)
            elif chart_type == 'scatter':
                fig = px.scatter(df, x=x_col, y=y_col)
            elif chart_type == 'stacked_bar':
                fig = px.bar(df, x=x_col, y=y_col)
            else:
                fig = px.bar(df, x=x_col, y=y_col)

            # Minimal styling
            fig.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=10, b=10),
                height=180,
                width=280,
                paper_bgcolor='white',
                plot_bgcolor='#F8F8F8',
                font=dict(size=8)
            )
            
            fig.update_xaxes(showticklabels=False, showgrid=False)
            fig.update_yaxes(showticklabels=False, showgrid=False)
            
            return fig
        except Exception as e:
            logger.warning(f"Mini chart creation failed for {chart_type}: {e}")
            # Return empty figure as fallback
            return go.Figure()
        
    def _get_svg_placeholders(self, suggestions: List[Dict]) -> Dict[str, str]:
        """SVG placeholder fallbacks"""
        
        svg_templates = {
            'line': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 180"><rect width="280" height="180" fill="#f8f8f8"/><polyline points="20,140 70,90 120,110 170,50 230,70" stroke="#47D7AC" stroke-width="3" fill="none"/><text x="140" y="160" text-anchor="middle" font-size="12" fill="#666">Line Chart</text></svg>',
            'bar': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 180"><rect width="280" height="180" fill="#f8f8f8"/><rect x="40" y="90" width="30" height="70" fill="#47D7AC"/><rect x="90" y="50" width="30" height="110" fill="#47D7AC"/><rect x="140" y="110" width="30" height="50" fill="#47D7AC"/><rect x="190" y="70" width="30" height="90" fill="#47D7AC"/><text x="140" y="170" text-anchor="middle" font-size="12" fill="#666">Bar Chart</text></svg>',
            'pie': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 180"><rect width="280" height="180" fill="#f8f8f8"/><circle cx="140" cy="85" r="60" fill="#47D7AC"/><path d="M140,85 L200,85 A60,60 0 0,1 170,135 Z" fill="#18483A"/><path d="M140,85 L170,135 A60,60 0 0,1 100,115 Z" fill="#6EDFC2"/><text x="140" y="170" text-anchor="middle" font-size="12" fill="#666">Pie Chart</text></svg>',
            'area': '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 280 180"><rect width="280" height="180" fill="#f8f8f8"/><polygon points="20,160 20,140 70,90 120,110 170,50 230,70 230,160" fill="#47D7AC" opacity="0.6"/><polyline points="20,140 70,90 120,110 170,50 230,70" stroke="#47D7AC" stroke-width="2" fill="none"/><text x="140" y="175" text-anchor="middle" font-size="12" fill="#666">Area Chart</text></svg>',
        }
        
        thumbnails = {}
        for suggestion in suggestions:
            chart_type = suggestion['chart_type']
            svg = svg_templates.get(chart_type, svg_templates['bar'])
            thumbnails[chart_type] = f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}"
        
        return thumbnails
    
    async def generate_chart(
        self,
        data: List[Dict],
        chart_type: str,
        title: str,
        config: Optional[Dict] = None,
        original_query: str = ""
    ) -> Dict[str, Any]:
        """Generate full interactive chart"""
        
        try:
            if not data:
                return {'error': 'No data', 'success': False}
            
            df = pd.DataFrame(data)
            config = config or {}
            
            try:
                x_col, y_cols = self._get_optimal_columns(df, chart_type, config)
            except ValueError as e:
                logger.warning(f"Manual detection failed: {e}, trying LLM...")
                x_col, y_cols = await self._get_columns_via_llm(df, chart_type, original_query)
            
            if not x_col or not y_cols:
                return {'error': str(e), 'success': False}
            logger.info(f"Chart config: x={x_col}, y={y_cols}, type={chart_type}")
            # Create chart
            fig = self._create_full_chart(df, chart_type, x_col, y_cols, title, config)
            
            # Apply theme
            fig.update_layout(
                template='plotly_white',
                font=dict(family='Arial', size=12),
                title_font=dict(size=18, color='#18483A', family='Arial'),
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                hovermode='x unified',
                height=350,
                margin=dict(l=50, r=50, t=80, b=50)
            )
            
            # Generate unique ID for this chart
            chart_id = str(uuid.uuid4())
            
            # Convert formats
            chart_json = fig.to_json()
            chart_html = fig.to_html(include_plotlyjs='cdn', full_html=True, div_id=f"chart-{chart_id}")
            
            # Generate PNG for PDF
            chart_png_bytes = fig.to_image(format="png", width=1200, height=800, scale=2)
            chart_png_base64 = base64.b64encode(chart_png_bytes).decode()
            
            followup_suggestions = []
            if original_query:
                followup_suggestions = await self.generate_intelligent_followup_suggestions(
                    original_query=original_query,
                    chart_type=chart_type,
                    data=data,
                    config={'x': x_col, 'y': y_cols}
                )
            
            return {
                'success': True,
                'chart_id': chart_id,
                'chart_json': chart_json,
                'chart_html': chart_html,
                'chart_png_base64': chart_png_base64,
                'chart_type': chart_type,
                'title': title,
                'data_points': len(df),
                'columns_used': {'x': x_col, 'y': y_cols},
                'timestamp': datetime.now().isoformat(),
                'followup_suggestions': followup_suggestions  # ← NEW
            }
            
        except Exception as e:
            logger.error(f"Chart generation error: {e}")
            return {'error': str(e), 'success': False}
    
    def _create_full_chart(self, df, chart_type, x_col, y_cols, title, config):
        """Create full-size chart"""
        
        if chart_type == 'line':
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Scatter(
                    x=df[x_col], y=df[y_col],
                    mode='lines+markers', name=y_col,
                    line=dict(width=3, color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)]),
                    marker=dict(size=8)
                ))
            
        elif chart_type in ['bar', 'grouped_bar']:
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Bar(
                    x=df[x_col], y=df[y_col], name=y_col,
                    marker_color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)]
                ))
            fig.update_layout(barmode='group')
            
        elif chart_type == 'stacked_bar':
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Bar(
                    x=df[x_col], y=df[y_col], name=y_col,
                    marker_color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)]
                ))
            fig.update_layout(barmode='stack')
            
        elif chart_type == 'area':
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Scatter(
                    x=df[x_col], y=df[y_col],
                    mode='lines', name=y_col,
                    fill='tonexty' if i > 0 else 'tozeroy',
                    line=dict(color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)])
                ))
            
        elif chart_type == 'pie':
            fig = px.pie(df, names=x_col, values=y_cols[0], color_discrete_sequence=self.NAGARRO_COLORS)
            
        elif chart_type == 'scatter':
            fig = px.scatter(df, x=x_col, y=y_cols[0], color=config.get('group_by'),
                           color_discrete_sequence=self.NAGARRO_COLORS)
        else:
            fig = px.bar(df, x=x_col, y=y_cols[0])
        
        fig.update_layout(title=title, xaxis_title=x_col, yaxis_title='Values')
        return fig
    
    async def generate_multi_chart_pdf(
        self,
        charts: List[Dict[str, Any]],
        title: str = "Analytics Report",
        user_name: str = "User"
    ) -> bytes:
        """
        Generate PDF with multiple charts
        Returns PDF bytes
        """
        
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
            
            story = []
            styles = getSampleStyleSheet()
            
            # Custom styles
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#18483A'),
                spaceAfter=30,
                alignment=1  # Center
            )
            
            subtitle_style = ParagraphStyle(
                'CustomSubtitle',
                parent=styles['Normal'],
                fontSize=12,
                textColor=colors.HexColor('#666666'),
                spaceAfter=20,
                alignment=1
            )
            
            chart_title_style = ParagraphStyle(
                'ChartTitle',
                parent=styles['Heading2'],
                fontSize=16,
                textColor=colors.HexColor('#47D7AC'),
                spaceAfter=10
            )
            
            # Report header
            story.append(Paragraph(title, title_style))
            story.append(Paragraph(f"Generated on {datetime.now().strftime('%B %d, %Y at %H:%M')}", subtitle_style))
            # story.append(Paragraph(f"Prepared for: {user_name}", subtitle_style))
            story.append(Spacer(1, 0.3*inch))
            
            # Add each chart
            for idx, chart in enumerate(charts, 1):
                if not chart.get('success'):
                    continue
                
                # Chart title
                chart_title_text = f"Chart {idx}: {chart.get('title', 'Untitled')}"
                story.append(Paragraph(chart_title_text, chart_title_style))
                story.append(Spacer(1, 0.1*inch))
                
                # Chart image
                png_base64 = chart.get('chart_png_base64')
                if png_base64:
                    img_data = base64.b64decode(png_base64)
                    img = RLImage(BytesIO(img_data), width=7*inch, height=4.5*inch)
                    story.append(img)
                
                # Chart metadata
                metadata_text = f"Type: {chart.get('chart_type', 'N/A')} | Data Points: {chart.get('data_points', 0)}"
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph(metadata_text, styles['Normal']))
                
                # Page break after each chart except last
                if idx < len(charts):
                    story.append(PageBreak())
            
            # Build PDF
            doc.build(story)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            
            return pdf_bytes
            
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            raise
    
    async def _fallback_suggestions(self, query: str, data: List[Dict]) -> Dict[str, Any]:
        """Rule-based fallback"""
        
        data_analysis = self._analyze_data(data)
        
        suggestions = []
        
        if data_analysis['is_time_series']:
            suggestions.append({
                'chart_type': 'line',
                'confidence': 85,
                'reasoning': 'Time series data detected - line chart shows trends best',
                'config': {'x': data_analysis['temporal_columns'][0], 'y': data_analysis['numeric_columns'][:1]},
                'title': 'Trend Analysis',
                'metadata': self.CHART_TYPES['line']
            })
        
        suggestions.append({
            'chart_type': 'bar',
            'confidence': 80,
            'reasoning': 'Bar chart provides clear comparison',
            'config': {'x': data_analysis['columns'][0], 'y': data_analysis['numeric_columns'][:1]},
            'title': 'Comparison Chart',
            'metadata': self.CHART_TYPES['bar']
        })
        
        if len(data_analysis['categorical_columns']) > 0 and len(data) < 10:
            suggestions.append({
                'chart_type': 'pie',
                'confidence': 75,
                'reasoning': 'Small dataset with categories - pie chart shows distribution',
                'config': {'x': data_analysis['categorical_columns'][0], 'y': data_analysis['numeric_columns'][:1]},
                'title': 'Distribution Breakdown',
                'metadata': self.CHART_TYPES['pie']
            })
        
        return {
            'success': True,
            'suggestions': suggestions[:3],
            'data_insights': 'Rule-based suggestion',
            'suggested_questions': []
        }
    async def generate_intelligent_followup_suggestions(
            self,
            original_query: str,
            chart_type: str,
            data: List[Dict],
            config: Dict[str, Any]
        ) -> List[Dict[str, Any]]:
            """
            Generate intelligent, context-aware follow-up suggestions
            using AI to understand query intent and data patterns
            """
            
            try:
                data_analysis = self._analyze_data(data)
                
                # Build AI prompt for follow-up suggestions
                followup_prompt = f"""
                                        You are an intelligent supply chain data analytics assistant. The user just generated a {chart_type} chart.

                                        **Original User Query:** {original_query}
                                        **Chart Type Generated:** {chart_type}
                                        **Data Configuration:**
                                        - X-axis: {config.get('x', 'N/A')}
                                        - Y-axis: {', '.join(config.get('y', []))}
                                        - Temporal columns: {', '.join(data_analysis['temporal_columns']) or 'None'}
                                        - Time series: {data_analysis['is_time_series']}
                                        - Date range: {data_analysis.get('date_range', 'N/A')}
                                        - Data points: {data_analysis['row_count']}

                                        **Context Analysis:**
                                        - Is weekly data: {'weekly' in original_query.lower() or 'week' in original_query.lower()}
                                        - Is monthly data: {'monthly' in original_query.lower() or 'month' in original_query.lower()}
                                        - Is projection: {'projection' in original_query.lower() or 'forecast' in original_query.lower()}
                                        - Is comparison: {'compare' in original_query.lower() or 'vs' in original_query.lower()}

                                        Generate 3-5 INTELLIGENT follow-up suggestions that would add value:

                                        **Rules:**
                                        1. If user asked for weekly data → suggest daily breakdown
                                        2. If user asked for monthly data → suggest weekly breakdown
                                        3. If it's a projection → suggest comparing with actuals/historical
                                        4. If single metric → suggest adding related metrics
                                        5. If time series → suggest different time periods (last month, last quarter)
                                        6. If categorical breakdown → suggest drilling down into subcategories
                                        7. If bar chart → suggest switching to trend view
                                        8. If line chart → suggest comparison with benchmarks

                                        Note:  
                                        - We have data from September 2025 onwards.
                                        - 
                                        **Output Format (JSON):**
                                        {{
                                        "suggestions": [
                                            {{
                                            "type": "granularity_change",  // or: comparison, metric_addition, time_period, drill_down, visualization_change
                                            "question": "Would you like to see the daily breakdown as well?",
                                            "reasoning": "Daily view would show more detailed patterns within the weekly trend",
                                            "action": {{
                                                "query_modification": "show daily trend for the same period",
                                                "chart_type": "line",
                                                "requires_new_data": true
                                            }}
                                            }},
                                            // ... more suggestions
                                        ]
                                        }}
                                        """
                
                response = await self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=[
                        {"role": "system", "content": "You are an intelligent supply chain data analytics assistant that provides context-aware follow-up suggestions."},
                        {"role": "user", "content": followup_prompt}
                    ],
                    temperature=0.4,
                    response_format={"type": "json_object"}
                )
                
                ai_suggestions = json.loads(response.choices[0].message.content)
                
                return ai_suggestions.get('suggestions', [])
                
            except Exception as e:
                logger.error(f"Follow-up suggestion error: {e}")
                return self._generate_rule_based_followups(original_query, chart_type, data_analysis)
        
    def _generate_rule_based_followups(
            self,
            query: str,
            chart_type: str,
            data_analysis: Dict
        ) -> List[Dict[str, Any]]:
            """Rule-based fallback for follow-up suggestions"""
            
            suggestions = []
            query_lower = query.lower()
            
            # Granularity suggestions
            if 'weekly' in query_lower or 'week' in query_lower:
                suggestions.append({
                    'type': 'granularity_change',
                    'question': 'Would you like to see the daily breakdown as well?',
                    'reasoning': 'Daily view provides more granular insights',
                    'action': {
                        'query_modification': 'show daily trend for the same period',
                        'chart_type': 'line',
                        'requires_new_data': True
                    }
                })
            
            if 'monthly' in query_lower or 'month' in query_lower:
                suggestions.append({
                    'type': 'granularity_change',
                    'question': 'Would you like to see the weekly breakdown?',
                    'reasoning': 'Weekly view shows patterns within each month',
                    'action': {
                        'query_modification': 'show weekly trend for the same period',
                        'chart_type': 'line',
                        'requires_new_data': True
                    }
                })
            
            if 'daily' in query_lower or 'day' in query_lower:
                suggestions.append({
                    'type': 'granularity_change',
                    'question': 'Would you like to see the aggregated weekly view?',
                    'reasoning': 'Weekly aggregation smooths out daily fluctuations',
                    'action': {
                        'query_modification': 'show weekly trend for the same period',
                        'chart_type': 'line',
                        'requires_new_data': True
                    }
                })
            
            # Projection/Forecast suggestions
            if 'projection' in query_lower or 'forecast' in query_lower:
                suggestions.append({
                    'type': 'comparison',
                    'question': 'Would you like to compare projected vs actual data?',
                    'reasoning': 'Comparison helps validate forecast accuracy',
                    'action': {
                        'query_modification': 'compare projected vs actual for the same period',
                        'chart_type': 'line',
                        'requires_new_data': True
                    }
                })
                
                suggestions.append({
                    'type': 'metric_addition',
                    'question': 'Do you want to see confidence intervals for the projection?',
                    'reasoning': 'Shows the range of uncertainty in forecasts',
                    'action': {
                        'query_modification': 'add confidence intervals to projection',
                        'chart_type': 'area',
                        'requires_new_data': True
                    }
                })
            
            # Comparison suggestions
            if 'shortfall' in query_lower or 'shortage' in query_lower:
                suggestions.append({
                    'type': 'drill_down',
                    'question': 'Would you like to see which specific SKUs or materials contribute most to the shortfall?',
                    'reasoning': 'Identifies root causes of shortfall',
                    'action': {
                        'query_modification': 'break down shortfall by SKU/material',
                        'chart_type': 'bar',
                        'requires_new_data': True
                    }
                })
            
            # Time period suggestions
            if data_analysis['is_time_series']:
                suggestions.append({
                    'type': 'time_period',
                    'question': 'Would you like to see the same analysis for the previous month/quarter?',
                    'reasoning': 'Historical comparison reveals trends',
                    'action': {
                        'query_modification': 'show same analysis for previous period',
                        'chart_type': chart_type,
                        'requires_new_data': True
                    }
                })
            
            # Chart type alternatives
            if chart_type == 'bar':
                suggestions.append({
                    'type': 'visualization_change',
                    'question': 'Would you prefer to see this as a trend line chart?',
                    'reasoning': 'Line charts better show patterns over time',
                    'action': {
                        'query_modification': 'same data',
                        'chart_type': 'line',
                        'requires_new_data': False
                    }
                })
            
            if chart_type == 'line' and data_analysis['has_multiple_metrics']:
                suggestions.append({
                    'type': 'visualization_change',
                    'question': 'Would you like to see individual metrics in separate charts?',
                    'reasoning': 'Separate charts make it easier to compare scales',
                    'action': {
                        'query_modification': 'split into multiple charts',
                        'chart_type': 'line',
                        'requires_new_data': False
                    }
                })
            
            # Drill-down suggestions
            if chart_type == 'pie' or 'breakdown' in query_lower:
                suggestions.append({
                    'type': 'drill_down',
                    'question': 'Would you like to see how this breakdown changes over time?',
                    'reasoning': 'Time-based view shows composition trends',
                    'action': {
                        'query_modification': 'show breakdown over time',
                        'chart_type': 'stacked_bar',
                        'requires_new_data': True
                    }
                })
            
            return suggestions[:5]
    
    async def generate_chart_title_by_llm(self, user_query: str, chart_type: str, data_sample: Dict) -> str:
        """
        Generate smart chart title using LLM.
        Called ONLY when keyword detection finds explicit chart type.
        """
        
        title_prompt = f"""User Query: "{user_query}"
                Chart Type: {chart_type}
                Data Sample: {str(data_sample)[:200]}

                Generate a concise, professional chart title (max 60 characters).
                Make it specific to what the data shows, not generic like "Chart Analysis".

                Examples:
                - "Projected Daily Quantities - Next 7 Days"
                - "Stock Levels by Location - December 2025"
                - "Revenue Distribution by Product Category"

                Respond with ONLY the title, no quotes or explanation."""
        
        try:
            response = await self.client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": title_prompt}],
                temperature=0.3,
                max_tokens=20
            )
            
            title = response.choices[0].message.content.strip().strip('"\'')
            # logger.info(f"📝 Generated title: {title}")
            return title
            
        except Exception as e:
            logger.warning(f"Failed to generate title via LLM: {e}")
            # Fallback to simple title
            return f"{chart_type.title()} Analysis"

    async def _detect_chart_type_by_LLM(self, user_query: str) -> str:
        # Ask LLM to determine chart type
            llm_chart_detection_prompt = f"""User query: "{user_query}"
                Determine if user is asking for a visualization and which chart type they want and explicitly mentioning.

                Available Chart Types: "line", "bar", "pie", "stacked bar", "area", "grounded bar", "scatter"
                Examples:
                -> User saying- show me line graph -> "line"
                -> show me distribution in pie chart -> "pie"

                Once determined the chart type, determine the short chart title based on user query
                Respond with JSON:
                {{
                    "chart_type": "line" or "bar" or "pie" or "area" or "scatter" or "none",
                    "chart_title":"suggested chart title",
                    "confidence": 0.0-1.0
                }}"""
            
            try:
                llm_response = await self.client.chat.completions.create(
                    model=self.NLP_LLM_model,
                    messages=[{"role": "user", "content": llm_chart_detection_prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.2
                )
                llm_analysis = json.loads(llm_response.choices[0].message.content)
                return llm_analysis
            except Exception as e:
                logger.warning(f"LLM chart detection failed: {e}, falling back to suggestions")
                return
            
    def _detect_chart_type_by_keywords(self, user_query: str) -> str:
        """
        Detect chart type from explicit keywords in user query.
        Only returns a chart type if user EXPLICITLY mentions it.
        Otherwise returns 'none' to trigger suggestions.
        """
        
        query_lower = user_query.lower().strip()
        
        # Define keyword mappings
        chart_keywords = {
            'line': [
                'line chart', 'line graph', 'line plot', 'trend line',
                'show me line', 'display line', 'line visualization',
            ],
            'bar': [
                'bar chart', 'bar graph', 'bar plot',
                'show me bar', 'display bar', 'bar visualization'
            ],
            'pie': [
                'pie chart', 'pie graph', 'pie plot',
                'show me pie', 'display pie', 'pie visualization',
                'distribution', 'breakdown'  # Implicit pie chart indicators
            ],
            'scatter': [
                'scatter chart', 'scatter graph', 'scatter plot',
                'show me scatter', 'display scatter',
                'correlation', 'relationship'  # Implicit scatter indicators
            ],
            'area': [
                'area chart', 'area graph', 'area plot',
                'show me area', 'display area', 'area visualization',
                'stacked area', 'area fill'
            ],
            'stacked bar': [
                'stacked bar', 'stacked bar chart', 'stacked bar graph',
                'grouped bar', 'multi-series bar'
            ],
            'grouped bar': [
                'grouped bar', 'side by side bar'
            ]
        }
        
        # Check for explicit keywords (higher priority)
        for chart_type, keywords in chart_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    # logger.info(f"✓ Found explicit keyword '{keyword}' → {chart_type}")
                    return chart_type
        
        # If no explicit chart type keyword found, return 'none'
        # This signals to show chart suggestions instead
        # logger.info("ℹ No explicit chart type keyword detected - will show suggestions")
        return 'none'
chart_service = ChartService()
