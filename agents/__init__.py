"""
Agent modules for the two-environment pipeline.

- SQLAgent: Generates and executes SQL queries over local parquet data
- InsightAgent: Produces natural language analysis and chart specifications
- PlotAgent: Renders visualizations from data and chart config - was changed to only generate the code for the visualization
"""

# lazy imports to avoid importing utils_copy when only PlotAgent is needed
# prevents TracerProvider conflicts in env2
def __getattr__(name):
    if name == "SQLAgent":
        from agents.sql_agent import SQLAgent
        return SQLAgent
    elif name == "InsightAgent":
        from agents.insight_agent import InsightAgent
        return InsightAgent
    elif name == "PlotAgent":
        from agents.plot_agent import PlotAgent
        return PlotAgent
    raise AttributeError(f"module 'agents' has no attribute '{name}'"

)

__all__ = ["SQLAgent", "InsightAgent", "PlotAgent"]

