"""Reusable loading and preparation of warehouse benchmark results."""

__all__ = [
    "create_summary_dataframe", "load_summary_jsons_fast", "load_new_results",
    "merge_results", "postprocess", "read_results", "validate_cohort", "write_results",
]


def __getattr__(name):
    if name in {"create_summary_dataframe", "load_summary_jsons_fast"}:
        from . import loading
        return getattr(loading, name)
    if name in __all__:
        from . import results
        return getattr(results, name)
    raise AttributeError(name)
