"""
Chart Service for RAG SQL - Interactive Visualizations
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ChartService:
    """Generate interactive, downloadable charts from SQL results"""
    
    CHART_TYPES = {
        'line': 'Line Chart - Trends over time',
        'bar': 'Bar Chart - Category comparisons',
        'stacked_bar': 'Stacked Bar - Part-to-whole by category',
        'area': 'Area Chart - Cumulative trends',
        'pie': 'Pie Chart - Composition breakdown',
        'scatter': 'Scatter Plot - Variable relationships',
        'heatmap': 'Heatmap - 2D patterns',
        'table': 'Data Table - Detailed view'
    }
    
    # Nagarro theme colors
    NAGARRO_COLORS = [
        '#47D7AC',  # Mint green
        '#18483A',  # Dark teal
        '#6EDFC2',  # Light mint
        '#2A6B5B',  # Medium teal
        '#8FE8D0',  # Pale mint
        '#0F2E24',  # Deep teal
    ]
    
    async def detect_visualization_intent(self, query: str, intent: str) -> Dict[str, Any]:
        """Detect if query needs visualization"""
        
        # Keywords that suggest visualization
        viz_keywords = [
            'graph', 'chart', 'plot', 'visualize', 'show', 'display',
            'projection', 'trend', 'forecast', 'breakdown', 'distribution',
            'over time', 'compare', 'analysis'
        ]
        
        query_lower = query.lower()
        needs_viz = any(keyword in query_lower for keyword in viz_keywords)
        
        # Force visualization for certain intents
        force_viz_intents = ['projection', 'trend_analysis', 'comparison']
        if intent in force_viz_intents:
            needs_viz = True
        
        return {
            'needs_visualization': needs_viz,
            'suggested_type': self._suggest_chart_type(query, intent),
            'query': query
        }
    
    def _suggest_chart_type(self, query: str, intent: str) -> Optional[str]:
        """Suggest appropriate chart type based on query"""
        query_lower = query.lower()
        
        # Time-based queries
        if any(word in query_lower for word in ['projection', 'forecast', 'trend', 'over time', 'daily', 'weekly', 'monthly']):
            return 'line'
        
        # Comparison queries
        if any(word in query_lower for word in ['compare', 'vs', 'versus', 'difference']):
            return 'bar'
        
        # Composition queries
        if any(word in query_lower for word in ['breakdown', 'composition', 'distribution', 'percentage', 'share']):
            return 'pie'
        
        # Default based on intent
        if intent in ['projection', 'trend_analysis']:
            return 'line'
        elif intent in ['comparison', 'analysis']:
            return 'bar'
        
        return 'bar'  # Default
    
    async def generate_chart(
        self,
        data: List[Dict],
        chart_type: str,
        title: str,
        config: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Generate Plotly chart from SQL results"""
        
        try:
            if not data or len(data) == 0:
                return {'error': 'No data available for visualization'}
            
            df = pd.DataFrame(data)
            config = config or {}
            
            # Auto-detect columns
            columns = list(df.columns)
            x_col = config.get('x_column') or columns[0]
            y_cols = config.get('y_columns') or [col for col in columns[1:] if pd.api.types.is_numeric_dtype(df[col])]
            
            if not y_cols:
                y_cols = [columns[1]] if len(columns) > 1 else [columns[0]]
            
            # Create chart based on type
            fig = self._create_chart(df, chart_type, x_col, y_cols, title, config)
            
            # Apply Nagarro theme
            fig.update_layout(
                template='plotly_white',
                font=dict(family='Arial', size=12),
                title_font=dict(size=16, color='#18483A', family='Arial'),
                plot_bgcolor='#FAFAFA',
                paper_bgcolor='white',
                hovermode='x unified',
                height=400,
                margin=dict(l=60, r=40, t=80, b=60),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            # Convert to formats
            chart_json = fig.to_json()
            chart_html = fig.to_html(include_plotlyjs='cdn', full_html=False)
            
            return {
                'success': True,
                'chart_json': chart_json,
                'chart_html': chart_html,
                'chart_type': chart_type,
                'title': title,
                'data_points': len(df),
                'columns_used': {'x': x_col, 'y': y_cols}
            }
            
        except Exception as e:
            logger.error(f"Chart generation error: {e}")
            return {'error': str(e), 'success': False}
    
    def _create_chart(self, df, chart_type, x_col, y_cols, title, config):
        """Create specific chart type"""
        
        if chart_type == 'line':
            fig = go.Figure()
            for y_col in y_cols:
                fig.add_trace(go.Scatter(
                    x=df[x_col],
                    y=df[y_col],
                    mode='lines+markers',
                    name=y_col,
                    line=dict(width=3),
                    marker=dict(size=8)
                ))
            fig.update_layout(title=title, xaxis_title=x_col, yaxis_title='Values')
            
        elif chart_type == 'bar':
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Bar(
                    x=df[x_col],
                    y=df[y_col],
                    name=y_col,
                    marker_color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)]
                ))
            fig.update_layout(title=title, xaxis_title=x_col, yaxis_title='Values', barmode='group')
            
        elif chart_type == 'stacked_bar':
            fig = go.Figure()
            for i, y_col in enumerate(y_cols):
                fig.add_trace(go.Bar(
                    x=df[x_col],
                    y=df[y_col],
                    name=y_col,
                    marker_color=self.NAGARRO_COLORS[i % len(self.NAGARRO_COLORS)]
                ))
            fig.update_layout(title=title, barmode='stack')
            
        elif chart_type == 'area':
            fig = go.Figure()
            for y_col in y_cols:
                fig.add_trace(go.Scatter(
                    x=df[x_col],
                    y=df[y_col],
                    mode='lines',
                    name=y_col,
                    fill='tonexty'
                ))
            fig.update_layout(title=title)
            
        elif chart_type == 'pie':
            y_col = y_cols[0]
            fig = px.pie(df, names=x_col, values=y_col, title=title, 
                        color_discrete_sequence=self.NAGARRO_COLORS)
            
        elif chart_type == 'scatter':
            y_col = y_cols[0]
            fig = px.scatter(df, x=x_col, y=y_col, title=title,
                           color=config.get('color_by'),
                           size=config.get('size_by'))
            
        elif chart_type == 'table':
            fig = go.Figure(data=[go.Table(
                header=dict(
                    values=list(df.columns),
                    fill_color='#47D7AC',
                    align='left',
                    font=dict(color='white', size=12)
                ),
                cells=dict(
                    values=[df[col] for col in df.columns],
                    fill_color=['#F0F9F6', 'white'] * (len(df.columns) // 2 + 1),
                    align='left'
                )
            )])
            fig.update_layout(title=title, height=min(500, 100 + len(df) * 30))
        
        else:
            # Default to bar
            fig = px.bar(df, x=x_col, y=y_cols[0], title=title)
        
        return fig
    
    async def suggest_refinements(
        self,
        query: str,
        chart_type: str,
        data_summary: Dict
    ) -> List[str]:
        """Generate conversational follow-up suggestions"""
        
        suggestions = []
        
        # Granularity suggestions
        if 'weekly' in query.lower():
            suggestions.append("Would you like to see the daily breakdown as well?")
        elif 'monthly' in query.lower():
            suggestions.append("Do you want to see the weekly trend?")
        
        # Projection-specific suggestions
        if 'projection' in query.lower() or 'forecast' in query.lower():
            suggestions.append("Would you like to compare projected vs actual data?")
            suggestions.append("Do you want to see confidence intervals?")
        
        # Chart type alternatives
        if chart_type == 'line':
            suggestions.append("Would you prefer to see this as a bar chart for easier comparison?")
        elif chart_type == 'bar':
            suggestions.append("Would you like to see the trend line instead?")
        elif chart_type == 'pie':
            suggestions.append("Would you like to see how this composition changes over time?")
        
        # Data-based suggestions
        if data_summary.get('has_multiple_series'):
            suggestions.append("Do you want to focus on specific SKUs or materials?")
        
        return suggestions[:3]  # Limit to 3 suggestions

chart_service = ChartService()
