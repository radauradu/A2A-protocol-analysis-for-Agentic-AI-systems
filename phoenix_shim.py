# phoenix_shim.py
"""
Makes legacy calls like:
    import phoenix as px
    px.Client().query_spans(...)
work against modern arize-phoenix.

- Ensures phoenix.Client exists
- Adds Client.query_spans(...) that forwards to Client.query(...)
"""

def ensure_phoenix_client():
    import phoenix as _phx
    # 1) Ensure top-level phoenix.Client exists
    if not hasattr(_phx, "Client"):
        from phoenix.client import Client as _Client
        _phx.Client = _Client

    # 2) Ensure phoenix.Client has query_spans(...)
    #    Some versions expose only .query(...)
    try:
        Client = _phx.Client
    except AttributeError:
        from phoenix.client import Client as _Client
        Client = _Client
        _phx.Client = Client

    if not hasattr(Client, "query_spans"):
        # define a tiny adapter
        def _query_spans(self, query, project_name: str, timeout=None):
            # newer Client typically has .query(...)
            if hasattr(self, "query"):
                return self.query(query, project_name=project_name, timeout=timeout)
            # if even .query is missing, raise a helpful error
            raise AttributeError(
                "phoenix.Client has neither 'query_spans' nor 'query'. "
                "Please upgrade 'arize-phoenix'."
            )
        Client.query_spans = _query_spans
