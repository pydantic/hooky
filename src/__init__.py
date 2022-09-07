def __getattr__(name):
    """
    This means `from src import app`, or `uvicorn src:app` works while allowing settings to be imported
    without importing views.
    """
    from .views import app

    return app
