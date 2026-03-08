import os
import json
import csv
from datetime import datetime
from typing import Dict, List, Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Import tracing; import from utils_copy for env3; fallback to global for env2 (A2A)
try:
    from utils_copy import tracer
    from opentelemetry.trace import StatusCode
    print(f"[PlotAgent] ✅ Using utils_copy tracer (env3): {tracer is not None}")
except Exception:
    # Fallback for env2 (A2A) which doesn't use utils_copy
    try:
        from opentelemetry import trace
        from opentelemetry.trace import StatusCode
        tracer = trace.get_tracer(__name__)
        print(f"[PlotAgent] ✅ Using global tracer (env2/A2A): {tracer is not None}")
    except Exception as e:
        print(f"[PlotAgent] ❌ Failed to get tracer: {e}")
        tracer = None
        StatusCode = None


def _ensure_run_dir() -> str:
    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    root = os.path.join('.', 'runs', ts)
    os.makedirs(root, exist_ok=True)
    return root


class PlotAgent:
    def run(self, rows: List[List], columns: List[str], chart_config: Dict, 
            run_id: Optional[str] = None, execution_id: Optional[str] = None) -> Dict:
        if not rows:
            raise ValueError("PlotAgent received empty rows. Cannot create visualization.")
        if not columns:
            raise ValueError("PlotAgent received empty columns. Cannot create visualization.")
        
        # Generate visualization code string for evaluation
        viz_code = f"""import matplotlib.pyplot as plt

# Data preparation
x = {columns}
y = ['example values']

plt.figure(figsize=(9, 4.5))
plt.plot(x, y, marker='o', linewidth=2)
plt.title('{chart_config.get('title', 'Chart')}')
plt.xlabel('{chart_config.get('x_axis', 'x')}')
plt.ylabel('{chart_config.get('y_axis', 'y')}')
plt.tight_layout()
plt.savefig('output.png', dpi=150)
plt.close()
"""
        
        # Trace the visualization generation 
        if tracer is not None:
            print(f"[PlotAgent] Creating gen_visualization span with run_id={run_id}, execution_id={execution_id}")

            try:
                with tracer.start_as_current_span("gen_visualization", openinference_span_kind="tool") as span:
                    # Use Phoenix span methods for input/output 
                    span.set_input({
                        "chart_config": chart_config,
                        "data_shape": f"{len(rows)} rows x {len(columns)} columns"
                    })
                    span.set_output(viz_code if len(viz_code) < 1000 else viz_code[:1000] + "...")
                    
                    # Other attributes
                    if run_id:
                        span.set_attribute("agentrun_id", run_id)
                        print(f"[PlotAgent] Set agentrun_id attribute: {run_id}")
                    if execution_id:
                        span.set_attribute("viz.execution_id", execution_id)
                    span.set_attribute("viz.chart_type", chart_config.get('chart_type', 'line'))
                    span.set_attribute("viz.row_count", len(rows))
                    
                    # Execute visualization creation inside span
                    result = self._create_visualization_internal(rows, columns, chart_config)
                    
                    if StatusCode:
                        span.set_status(StatusCode.OK)
                    
                    print(f"[PlotAgent] ✅ Span created and completed")
                    return result
            except TypeError:
                # Fallback if openinference_span_kind not supported
                with tracer.start_as_current_span("gen_visualization") as span:
                    span.set_input({
                        "chart_config": chart_config,
                        "data_shape": f"{len(rows)} rows x {len(columns)} columns"
                    })
                    span.set_output(viz_code if len(viz_code) < 1000 else viz_code[:1000] + "...")
                    if run_id:
                        span.set_attribute("agentrun_id", run_id)
                    if execution_id:
                        span.set_attribute("viz.execution_id", execution_id)
                    span.set_attribute("viz.chart_type", chart_config.get('chart_type', 'line'))
                    span.set_attribute("viz.row_count", len(rows))
                    result = self._create_visualization_internal(rows, columns, chart_config)
                    if StatusCode:
                        span.set_status(StatusCode.OK)
                    print(f"[PlotAgent] ✅ Span created and completed (fallback)")
                    return result
        else:
            # If no tracing ->just create visualization
            print(f"[PlotAgent] ⚠️  Tracer is None, skipping span creation")
            return self._create_visualization_internal(rows, columns, chart_config)
    
    def _create_visualization_internal(self, rows: List[List], columns: List[str], chart_config: Dict) -> Dict:
        """Internal method to actually create the visualization"""
        out_dir = _ensure_run_dir()

        # Save CSV
        csv_path = os.path.join(out_dir, 'data.csv')
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)

        # Save chart config JSON
        cfg_path = os.path.join(out_dir, 'chart_config.json')
        with open(cfg_path, 'w') as f:
            json.dump(chart_config, f)

        # Plot (won't be used)
        fig_path = os.path.join(out_dir, 'fig.png')
        x_key = chart_config.get('x_axis')
        y_key = chart_config.get('y_axis')
        title = chart_config.get('title', 'Chart')
        chart_type = chart_config.get('chart_type', 'line')

        # Build series
        idx_x = columns.index(x_key) if x_key in columns else 0
        idx_y = columns.index(y_key) if y_key in columns else 1 if len(columns) > 1 else 0
        x = [r[idx_x] for r in rows]
        y = [r[idx_y] for r in rows]

        # Try to parse YYYY-MM-DD date strings
        from datetime import datetime as _dt
        def _parse_date_safe(v):
            try:
                return _dt.strptime(str(v), "%Y-%m-%d")
            except Exception:
                return v
        x_parsed = [_parse_date_safe(v) for v in x]

        has_dates = any(hasattr(v, "year") for v in x_parsed)
        if has_dates:
            pairs = sorted(zip(x_parsed, y), key=lambda t: t[0])
            x_parsed, y = [p[0] for p in pairs], [p[1] for p in pairs]
            x = x_parsed

        plt.figure(figsize=(9, 4.5))
        if chart_type == 'bar':
            plt.bar(x, y)
        else:
            plt.plot(x, y, marker='o', linewidth=2)

        plt.title(title)
        plt.xlabel(x_key or 'x')
        plt.ylabel(y_key or 'y')
        plt.tight_layout()
        
        # Format date axis if x contains dates
        try:
            import matplotlib.dates as mdates
            if has_dates:
                plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator())
                plt.gca().xaxis.set_major_formatter(mdates.ConciseDateFormatter(mdates.AutoDateLocator()))
                plt.gcf().autofmt_xdate()
        except Exception:
            pass
            
        plt.savefig(fig_path, dpi=150)
        plt.close()

        return {
            "image_path": fig_path,
            "csv_path": csv_path,
            "chart_config_path": cfg_path,
        }


