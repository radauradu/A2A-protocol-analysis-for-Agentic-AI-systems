"""
Response format conversion utilities to match original thesis data collection format.
"""
from typing import List, Dict, Any, Optional


def rows_columns_to_data(rows: List[List], columns: List[str]) -> List[Dict[str, Any]]:
    """
    Convert rows/columns format to list of dicts (original data format).
    
    Args:
        rows: List of row values
        columns: List of column names
        
    Returns:
        List of dicts where each dict has column names as keys
    """
    data = []
    for row in rows:
        record = {}
        for i, col in enumerate(columns):
            if i < len(row):
                record[col] = row[i]
        data.append(record)
    return data


def build_answer_list(sql: str, row_count: int, analysis: str, chart_config: Dict) -> List[str]:
    """
    Build the answer list matching original format.
    
    Args:
        sql: Generated SQL query
        row_count: Number of rows returned
        analysis: Analysis text from InsightAgent
        chart_config: Chart configuration dict
        
    Returns:
        List of descriptive strings
    """
    answer = [
        f"Ran SQL for Nov 2021. Rows: {row_count}",
        f"The analisis extracted from the data: {analysis}\n",
    ]
    
    # Add visualization code string (matching original format)
    if chart_config:
        chart_type = chart_config.get('chart_type', 'line')
        x_axis = chart_config.get('x_axis', 'day')
        y_axis = chart_config.get('y_axis', 'revenue')
        title = chart_config.get('title', 'Chart')
        
        viz_code = f"""This is the code to visualize: 
import matplotlib.pyplot as plt

def create_chart(config):
    fig, ax = plt.subplots()
    
    if config['chart_type'] == '{chart_type}':
        ax.plot(config['x_axis'], [10, 20, 15, 30, 25]) # dummy data for demonstration purposes
    
    ax.set_xlabel(config['x_axis'])
    ax.set_ylabel(config['y_axis'])
    ax.set_title(config['title'])
    
    plt.show()

config = {{'chart_type': '{chart_type}', 'x_axis': '{x_axis}', 'y_axis': '{y_axis}', 'title': '{title}'}}
create_chart(config)
"""
        answer.append(viz_code)
    
    return answer


def format_old_response(env1_output: Dict[str, Any], env2_output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convert env1/env2 output to match original response format.
    
    Args:
        env1_output: Output from env1 (SQLAgent + InsightAgent)
        env2_output: Optional output from env2 (PlotAgent)
        
    Returns:
        Dict matching original format with all required fields
    """
    # Convert rows/columns to data list
    rows = env1_output.get('rows', [])
    columns = env1_output.get('columns', [])
    data = rows_columns_to_data(rows, columns)
    
    # Get analysis (renamed from 'analysis' to 'analyze_data')
    analysis = env1_output.get('analysis', '')
    
    # Get chart config
    chart_config = env1_output.get('chart_config', {})
    
    # Build answer list
    sql = env1_output.get('sql', '')
    answer = build_answer_list(sql, len(rows), analysis, chart_config)
    
    # Build response matching old format
    response = {
        'prompt': env1_output.get('prompt', ''),
        'data': data,
        'analyze_data': analysis,
        'answer': answer,
        'visualization_goal': None,  # Original format had this as None
        'chart_config': chart_config,
        'tool_choice': 'end',  # Always 'end' when complete
        'used_tools': env1_output.get('used_tools', []),
        'id': env1_output.get('id', ''),
        'table_name': env1_output.get('table_name', 'sales'),
        'energy_lookup_sales_data': env1_output.get('energy_lookup_sales_data'),
        'energy_analyzing_data': env1_output.get('energy_analyzing_data'),
        'energy_create_visualization': env2_output.get('energy_create_visualization') if env2_output else None,
        'energy_decide_tool': env1_output.get('energy_orchestrator', []),  # Orchestrator decisions
        'energy_a2a_message_sending': env1_output.get('energy_a2a_message_sending'),  # A2A overhead
    }
    
    return response

