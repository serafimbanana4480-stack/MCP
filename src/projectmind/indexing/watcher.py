def watch(*args, **kwargs):
    """Optional watchfiles integration point; callers can run it in a worker."""
    try:
        from watchfiles import watch as watchfiles_watch

        return watchfiles_watch(*args, **kwargs)
    except ImportError:
        return iter(())
